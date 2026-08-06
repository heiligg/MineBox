"""Checkpoint 7 — installer, image packaging, systemd, SoftAP render."""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InstallerScriptTests(unittest.TestCase):
    def test_install_sh_idempotent_flags(self) -> None:
        text = _read(APP / "install.sh")
        for flag in ("--dry-run", "--uninstall", "--skip-packages", "--no-display"):
            self.assertIn(flag, text)
        self.assertIn("services/sudoers/minebox", text)
        self.assertIn("minebox_render_hotspot_configs.py", text)
        self.assertIn("minebox_validate_install.py", text)
        self.assertIn("rsync -a --delete", text)
        self.assertIn("/var/lib/minebox", text)
        self.assertIn("preserving user data", text.lower())

    def test_canonical_sudoers_contents(self) -> None:
        text = _read(APP / "services" / "sudoers" / "minebox")
        self.assertIn("restart hostapd.service", text)
        self.assertIn("restart dnsmasq.service", text)
        self.assertIn("minebox_render_hotspot_configs.py", text)
        self.assertIn("minebox_set_os_password.py", text)
        self.assertIn("nft -f /etc/nftables.conf", text)
        self.assertIn("reload ssh", text)

    def test_update_apply_uses_canonical_sudoers(self) -> None:
        text = _read(APP / "scripts" / "minebox_update_apply.py")
        self.assertIn('services" / "sudoers" / "minebox"', text)
        self.assertIn("minebox_render_hotspot_configs.py", text)


class PiGenImageTests(unittest.TestCase):
    def test_packages_include_kiosk_stack(self) -> None:
        pkgs = _read(
            ROOT / "pi-gen" / "stage-minebox" / "00-install-minebox" / "00-packages"
        )
        for name in ("chromium", "xinit", "openbox", "hostapd", "dnsmasq", "nftables", "plymouth"):
            self.assertIn(name, pkgs)
        self.assertNotIn("||", pkgs)

    def test_chroot_installs_sudoers_file(self) -> None:
        text = _read(
            ROOT
            / "pi-gen"
            / "stage-minebox"
            / "00-install-minebox"
            / "00-run-chroot.sh"
        )
        self.assertIn("services/sudoers/minebox", text)
        self.assertIn("minebox-display.service", text)
        self.assertIn("chromium", text)

    def test_firstboot_renders_hotspot(self) -> None:
        text = _read(
            ROOT
            / "pi-gen"
            / "stage-minebox"
            / "01-system-config"
            / "files"
            / "minebox-firstboot"
        )
        self.assertIn("minebox_render_hotspot_configs.py", text)

    def test_hotspot_chroot_calls_renderer(self) -> None:
        text = _read(
            ROOT
            / "pi-gen"
            / "stage-minebox"
            / "02-dedicated-hotspot"
            / "02-run-chroot.sh"
        )
        self.assertIn("minebox_render_hotspot_configs.py", text)
        self.assertNotIn("network-online.target", text)


class SystemdOrderingTests(unittest.TestCase):
    def test_api_not_blocked_on_network_online(self) -> None:
        api = _read(APP / "services" / "minebox-api.service")
        self.assertNotIn("network-online.target", api)
        self.assertIn("After=", api)
        self.assertIn("StartLimitBurst=", api)
        self.assertIn("Restart=on-failure", api)
        self.assertIn("SupplementaryGroups=gpio input", api)
        self.assertNotIn("DeviceAllow=", api)
        self.assertIn("usermod -aG gpio,input minebox", api)

    def test_captive_after_api_hostapd(self) -> None:
        captive = _read(APP / "services" / "minebox-captive.service")
        self.assertNotIn("network-online.target", captive)
        self.assertIn("minebox-api.service", captive)
        self.assertIn("hostapd.service", captive)

    def test_ui_uses_main_py_and_start_limit(self) -> None:
        ui = _read(
            ROOT
            / "pi-gen"
            / "stage-minebox"
            / "01-system-config"
            / "files"
            / "minebox-ui.service"
        )
        self.assertIn("ExecStart=/usr/bin/python3 /opt/minebox/main.py", ui)
        self.assertNotIn("network-online.target", ui)
        self.assertIn("StartLimitBurst=", ui)
        self.assertIn("Restart=on-failure", ui)

    def test_minecraft_uses_launcher(self) -> None:
        for rel in (
            APP / "services" / "minecraft.service",
            ROOT / "systemd" / "minecraft.service",
            ROOT
            / "pi-gen"
            / "stage-minebox"
            / "01-system-config"
            / "files"
            / "minecraft.service",
        ):
            text = _read(rel)
            self.assertIn("python3 -m services.launcher", text, msg=str(rel))
            self.assertIn("StartLimitBurst=5", text, msg=str(rel))

    def test_display_wants_api(self) -> None:
        disp = _read(APP / "services" / "minebox-display.service")
        self.assertIn("After=minebox-api.service", disp)
        self.assertIn("xinit", disp)
        self.assertIn("StartLimitBurst=", disp)

    def test_no_sleep_in_unit_files(self) -> None:
        units = list((APP / "services").glob("*.service"))
        units += list(
            (
                ROOT / "pi-gen" / "stage-minebox" / "01-system-config" / "files"
            ).glob("*.service")
        )
        for path in units:
            text = _read(path)
            self.assertNotRegex(
                text,
                r"(?i)ExecStart.*=.*/bin/(?:sleep|bash\s+-c\s+['\"]sleep)",
                msg=f"sleep hack in {path}",
            )


class SoftAPRenderTests(unittest.TestCase):
    def _load_render(self, name: str):
        os.environ["MINEBOX_APP_DIR"] = str(APP)
        return _load_module(
            name,
            APP / "scripts" / "minebox_render_hotspot_configs.py",
        )

    def test_render_dry_run_substitutes_iface(self) -> None:
        mod = self._load_render("minebox_render_hotspot_configs")
        # Module caches APP_ROOT at import — patch for this process.
        mod.APP_ROOT = APP
        mod.TEMPLATE_DIR = APP / "services" / "hotspot"
        result = mod.render("wlan1", dry_run=True, write_nft=False)
        self.assertEqual(result["hotspot_iface"], "wlan1")
        self.assertTrue(any("hostapd" in f for f in result["files"]))

    def test_replace_iface_helper(self) -> None:
        mod = self._load_render("minebox_render_hotspot_configs2")
        out = mod._replace_iface("interface=wlan0\n", "wlan0", "wlan1")
        self.assertIn("interface=wlan1", out)
        out2 = mod._replace_iface('iifname "wlan0"', "wlan0", "wlp1s0")
        self.assertIn('iifname "wlp1s0"', out2)

    def test_cli_dry_run_exit_zero(self) -> None:
        mod = self._load_render("minebox_render_hotspot_configs3")
        mod.APP_ROOT = APP
        mod.TEMPLATE_DIR = APP / "services" / "hotspot"
        code = mod.main(["--dry-run", "--iface", "wlan1", "--skip-nft"])
        self.assertEqual(code, 0)


class ValidateInstallTests(unittest.TestCase):
    def test_validate_module_loads(self) -> None:
        mod = _load_module(
            "minebox_validate_install",
            APP / "scripts" / "minebox_validate_install.py",
        )
        results = mod.run_checks()
        self.assertTrue(any(r["label"].startswith("path:") for r in results))
        # On developer machines /opt/minebox is usually missing — expect hard fails,
        # but the runner must not crash.
        code = mod.main(["--json"])
        self.assertIn(code, (0, 1))

    def test_docs_present(self) -> None:
        docs = ROOT / "docs" / "v1"
        for name in (
            "Installer.md",
            "Image_Build.md",
            "Appliance_Recovery.md",
            "Systemd_Services.md",
        ):
            self.assertTrue((docs / name).is_file(), msg=name)


class CorruptConfigScenarioTests(unittest.TestCase):
    def test_invalid_iface_rejected(self) -> None:
        os.environ["MINEBOX_APP_DIR"] = str(APP)
        mod = _load_module(
            "minebox_render_hotspot_configs4",
            APP / "scripts" / "minebox_render_hotspot_configs.py",
        )
        mod.APP_ROOT = APP
        mod.TEMPLATE_DIR = APP / "services" / "hotspot"
        code = mod.main(["--iface", "bad iface;rm", "--dry-run", "--skip-nft"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
