from __future__ import annotations
import curses
import os
import sys
import time
from typing import Callable, Optional

from config import APP_VERSION
from status import get_system_status
from services import backups, minecraft, rcon, settings as settings_service
from services import system as system_service
from services import diagnostics, log_tools, monitoring, validation

Action = Optional[Callable[[], None]]

class MineBoxApp:
    def __init__(self, screen: curses.window) -> None:
        self.screen = screen
        self.running = True
        self.settings = settings_service.load()
        try: curses.curs_set(0)
        except curses.error: pass
        self.screen.keypad(True)
        self._init_colors()

    def _init_colors(self) -> None:
        self.color_title = curses.A_BOLD
        self.color_ok = curses.A_BOLD
        self.color_warn = curses.A_BOLD
        self.color_bad = curses.A_BOLD
        self.color_selected = curses.A_REVERSE | curses.A_BOLD
        if not curses.has_colors():
            return
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
            curses.init_pair(4, curses.COLOR_RED, -1)
            curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_CYAN)
            self.color_title = curses.color_pair(1) | curses.A_BOLD
            self.color_ok = curses.color_pair(2) | curses.A_BOLD
            self.color_warn = curses.color_pair(3) | curses.A_BOLD
            self.color_bad = curses.color_pair(4) | curses.A_BOLD
            self.color_selected = curses.color_pair(5) | curses.A_BOLD
        except curses.error:
            pass

    def safe(self, row: int, col: int, text: object, attr: int = 0) -> None:
        h, w = self.screen.getmaxyx()
        if 0 <= row < h and 0 <= col < w - 1:
            try: self.screen.addstr(row, col, str(text)[:max(0, w-col-1)], attr)
            except curses.error: pass

    def title(self, text: str) -> int:
        self.screen.erase(); _, w = self.screen.getmaxyx(); line = "=" * max(1, w-1)
        self.safe(0, 0, line, self.color_title)
        self.safe(1, max(0, (w-len(text))//2), text, self.color_title)
        self.safe(2, 0, line, self.color_title)
        return 4

    def footer(self, text: str) -> None:
        h, w = self.screen.getmaxyx(); self.safe(h-2, 0, "-" * max(1, w-1)); self.safe(h-1, 0, text)

    @staticmethod
    def is_select(key: int) -> bool:
        return key in (10, 13, curses.KEY_ENTER)

    @staticmethod
    def is_back(key: int) -> bool:
        # Left arrow represents the future physical Left/Back button.
        return key in (curses.KEY_LEFT, 27, curses.KEY_BACKSPACE, 127)

    @staticmethod
    def is_quick(key: int) -> bool:
        # Right arrow represents the future physical Right/Quick button.
        return key == curses.KEY_RIGHT

    def quick_actions(self) -> None:
        self.menu("Quick Actions", [
            ("Save World", self.save_world),
            ("Backup Now", self.create_backup),
            ("Restart Server", self.restart_server),
            ("Stop Server", self.stop_server),
            ("System Status", self.system_info),
            ("Return", None),
        ], "Rotate: Move | Press: Select | Left: Back")

    def run(self) -> None:
        while self.running:
            if self.dashboard() == "menu": self.main_menu()

    def dashboard(self) -> str:
        self.screen.timeout(int(self.settings.get("refresh_seconds", 2) * 1000))
        while self.running:
            s = get_system_status(); online = minecraft.is_running(); monitoring.sample(); row = self.title("MineBox OS")
            temp = str(s["temperature"])
            lines = [
                f"Minecraft:       {'ONLINE' if online else 'OFFLINE'}",
                f"Players:         {minecraft.player_count_text()}",
                f"Version:         {minecraft.version()}",
                f"Server Uptime:   {minecraft.uptime()}", "",
                f"CPU Usage:       {s['cpu']}%",
                f"Memory Usage:    {s['memory']}%",
                f"Disk Usage:      {s['disk']}%",
                f"Temperature:     {temp}",
                f"IP Address:      {s['ip_address']}",
                f"System Uptime:   {s['uptime']}",
            ]
            warnings = []
            if float(s["cpu"]) >= 90: warnings.append("WARNING: CPU usage is high")
            if float(s["memory"]) >= 90: warnings.append("WARNING: Memory usage is high")
            if float(s["disk"]) >= 90: warnings.append("WARNING: Disk is almost full")
            last_backup = backups.legacy_list_backups()
            lines.insert(5, f"Last Backup:     {last_backup[0].label if last_backup else 'None'}")
            if diagnostics.log_has_recent_error(): warnings.append("WARNING: Recent server errors detected")
            for line in lines + ([""] + warnings if warnings else []):
                attr = 0
                if line.startswith("Minecraft:"): attr = self.color_ok if online else self.color_bad
                elif line.startswith("WARNING:"): attr = self.color_warn
                self.safe(row, 2, line, attr); row += 1
            self.footer("Left: Exit UI | Press: Menu | Right: Quick Actions")
            self.screen.refresh(); key = self.screen.getch()
            if self.is_select(key): self.screen.timeout(-1); return "menu"
            if self.is_quick(key):
                self.screen.timeout(-1); self.quick_actions(); self.screen.timeout(int(self.settings.get("refresh_seconds", 2) * 1000))
            elif self.is_back(key):
                if self.confirm("Exit MineBox UI?", ["Minecraft will keep running."], "Exit UI"):
                    self.running = False; return "exit"
                self.screen.timeout(int(self.settings.get("refresh_seconds", 2) * 1000))
        return "exit"

    def menu(self, title: str, items: list[tuple[str, Action]], footer: str = "Rotate: Move | Press: Select | Left: Back | Right: Quick") -> None:
        selected = 0; self.screen.timeout(-1)
        while self.running:
            row = self.title(title)
            for i, (label, _) in enumerate(items):
                self.safe(row, 2, ("> " if i == selected else "  ") + label, self.color_selected if i == selected else 0); row += 1
            self.footer(footer); self.screen.refresh(); key = self.screen.getch()
            if key == curses.KEY_UP: selected = (selected-1) % len(items)
            elif key == curses.KEY_DOWN: selected = (selected+1) % len(items)
            elif self.is_select(key):
                action = items[selected][1]
                if action is None: return
                action()
            elif self.is_quick(key) and title != "Quick Actions": self.quick_actions()
            elif self.is_back(key): return

    def choose_option(self, title: str, labels: list[str], footer: str = "Rotate: Move | Press: Select | Left: Back") -> int | None:
        selected = 0; self.screen.timeout(-1)
        while self.running:
            row = self.title(title)
            for i, label in enumerate(labels):
                self.safe(row, 2, ("> " if i == selected else "  ") + label, self.color_selected if i == selected else 0); row += 1
            self.footer(footer); self.screen.refresh(); key = self.screen.getch()
            if key == curses.KEY_UP: selected = (selected - 1) % len(labels)
            elif key == curses.KEY_DOWN: selected = (selected + 1) % len(labels)
            elif self.is_select(key): return selected
            elif self.is_back(key): return None

    def main_menu(self) -> None:
        self.menu("Main Menu", [
            ("Minecraft Server", self.server_menu), ("Live Console", self.live_console),
            ("Players", self.players_menu), ("Backups", self.backups_menu),
            ("Server Settings", self.server_settings_menu), ("Worlds & Software", self.worlds_software_menu),
            ("Performance", self.performance_screen), ("Log Browser", self.log_browser),
            ("MineBox Settings", self.minebox_settings_menu), ("Diagnostics", self.diagnostics_menu),
            ("System", self.system_menu), ("About MineBox", self.about), ("Exit MineBox UI", self.exit_ui)
        ], "Rotate: Move | Press: Select | Left: Dashboard | Right: Quick")

    def message(self, title: str, lines: list[str], wait: bool = True) -> None:
        row = self.title(title)
        for line in lines:
            for wrapped in self.wrap(line): self.safe(row, 2, wrapped); row += 1
        self.footer("Press/Left: Return" if wait else "Please wait..."); self.screen.refresh()
        if wait:
            self.screen.timeout(-1)
            while True:
                key = self.screen.getch()
                if self.is_select(key) or self.is_back(key): break

    def wrap(self, text: str) -> list[str]:
        _, w = self.screen.getmaxyx(); width = max(10, w-5)
        if not text: return [""]
        words = text.split(); lines=[]; current=""
        for word in words:
            test = word if not current else current + " " + word
            if len(test) <= width: current=test
            else: lines.append(current); current=word
        if current: lines.append(current)
        return lines

    def confirm(self, title: str, lines: list[str], yes: str = "Yes") -> bool:
        choice = 0
        while True:
            row = self.title(title)
            for line in lines: self.safe(row, 2, line); row += 1
            row += 1
            for i, label in enumerate(["Cancel", yes]): self.safe(row+i, 2, ("> " if i==choice else "  ")+label, curses.A_REVERSE|curses.A_BOLD if i==choice else 0)
            self.footer("Rotate: Choose | Press: Confirm | Left: Cancel"); self.screen.refresh(); key=self.screen.getch()
            if key in (curses.KEY_UP,curses.KEY_DOWN): choice=1-choice
            elif self.is_select(key): return choice==1
            elif self.is_back(key): return False

    def result(self, title: str, result) -> None:
        self.message(title, [result.stdout or ("Completed successfully." if result.ok else result.message)] if result.ok else ["Operation failed:", result.message])

    def text_input(self, title: str, prompt: str, initial: str = "", max_len: int = 80) -> str | None:
        value = initial
        try: curses.curs_set(1)
        except curses.error: pass
        self.screen.timeout(-1)
        while True:
            row=self.title(title); self.safe(row,2,prompt); self.safe(row+2,2,value+"_"); self.footer("Press: Save | Left: Cancel | Backspace: Delete"); self.screen.refresh(); key=self.screen.getch()
            if self.is_select(key):
                try: curses.curs_set(0)
                except curses.error: pass
                return value
            if self.is_back(key):
                try: curses.curs_set(0)
                except curses.error: pass
                return None
            if key in (curses.KEY_BACKSPACE,127,8): value=value[:-1]
            elif 32 <= key <= 126 and len(value)<max_len: value += chr(key)

    def server_menu(self) -> None:
        self.menu("Minecraft Server", [("Start Server", self.start_server),("Stop Server", self.stop_server),("Restart Server", self.restart_server),("Save World", self.save_world),("Server Information", self.server_info),("Live Console", self.live_console),("Back",None)])

    def start_server(self): self.message("Minecraft Server", ["Starting Minecraft..."], False); self.result("Minecraft Server", minecraft.start())
    def save_world(self): self.message("Minecraft Server", ["Saving world..."], False); self.result("Minecraft Server", minecraft.save_world())
    def stop_server(self):
        if (not self.settings.get("confirm_server_actions",True)) or self.confirm("Stop Server?", ["The world will be saved first.", "Connected players will be disconnected."], "Stop Server"):
            self.message("Minecraft Server", ["Saving and stopping Minecraft..."], False); self.result("Minecraft Server", minecraft.stop())
    def restart_server(self):
        if (not self.settings.get("confirm_server_actions",True)) or self.confirm("Restart Server?", ["The world will be saved first.", "Connected players will be disconnected."], "Restart Server"):
            self.message("Minecraft Server", ["Saving and restarting Minecraft..."], False); self.result("Minecraft Server", minecraft.restart())

    def server_info(self):
        props, err = minecraft.read_properties()
        self.message("Server Information", [f"Status: {minecraft.status_text()}",f"Players: {minecraft.player_count_text()}",f"Version: {minecraft.version()}",f"Uptime: {minecraft.uptime()}",f"MOTD: {props.get('motd','Unknown') if not err else 'Unavailable'}",f"Game mode: {props.get('gamemode','Unknown')}",f"Difficulty: {props.get('difficulty','Unknown')}"])

    def live_console(self) -> None:
        offset=0; self.screen.timeout(1000)
        while self.running:
            h,_=self.screen.getmaxyx(); available=max(3,h-7); logs=minecraft.recent_logs(max(available+offset,available)); shown=logs[max(0,len(logs)-available-offset):len(logs)-offset if offset else None]
            row=self.title("Live Console")
            for line in shown[-available:]: self.safe(row,1,line); row+=1
            self.footer("Rotate: Scroll | Left: Back | Right: Command"); self.screen.refresh(); key=self.screen.getch()
            if key==curses.KEY_UP: offset=min(offset+1,max(0,len(logs)-available))
            elif key==curses.KEY_DOWN: offset=max(0,offset-1)
            elif self.is_quick(key):
                command=self.text_input("RCON Command","Enter command without a leading slash:")
                if command: self.result("RCON Result", rcon.send(command))
            elif self.is_back(key): self.screen.timeout(-1); return

    def players_menu(self) -> None:
        info=minecraft.player_info()
        if info is None: self.message("Players", ["Minecraft is offline or RCON is unavailable."]); return
        names,max_players=info
        items=[(f"{name}", lambda n=name:self.player_actions(n)) for name in names]
        items += [("Broadcast Message", self.broadcast),("Refresh", self.players_menu),("Back",None)]
        self.menu(f"Players ({len(names)}/{max_players})", items)

    def player_actions(self, name: str) -> None:
        self.menu(name, [("Kick Player", lambda:self.kick(name)),("Ban Player", lambda:self.ban(name)),("OP Player", lambda:self.simple_player_command("op",name)),("De-OP Player", lambda:self.simple_player_command("deop",name)),("Add to Whitelist", lambda:self.whitelist(name)),("Remove from Whitelist", lambda:self.simple_player_command("whitelist remove",name)),("Back",None)])
    def kick(self,name):
        reason=self.text_input("Kick Player","Optional reason:")
        if reason is not None and self.confirm("Kick Player?",[f"Kick {name}?"],"Kick"): self.result("Kick Player",rcon.send(f"kick {name} {reason}".strip()))
    def ban(self,name):
        reason=self.text_input("Ban Player","Optional reason:")
        if reason is not None and self.confirm("Ban Player?",[f"Ban {name}?"],"Ban"): self.result("Ban Player",rcon.send(f"ban {name} {reason}".strip()))
    def whitelist(self,name): self.result("Whitelist",rcon.send(f"whitelist add {name}"))
    def simple_player_command(self, command, name): self.result("Player Management", rcon.send(f"{command} {name}"))
    def broadcast(self):
        text=self.text_input("Broadcast","Message to all online players:")
        if text: self.result("Broadcast",rcon.send(f"say {text}"))

    def backups_menu(self) -> None:
        self.menu("Backups", [("Create Backup",self.create_backup),("Restore Backup",self.restore_backup_menu),("Delete Backup",self.delete_backup_menu),("Prune Old Backups",self.prune_backups),("Backup Information",self.backup_info),("Back",None)])
    def create_backup(self): self.message("Backup",["Saving world and creating backup..."],False); self.result("Backup",backups.create())
    def prune_backups(self):
        if self.confirm("Prune Backups?", [f"Keep newest {self.settings.get('backup_retention',10)} backup(s)."], "Prune"):
            self.result("Backups", backups.prune())
    def backup_info(self):
        items=backups.legacy_list_backups(); total=sum(x.size for x in items)
        self.message("Backup Information", [f"Backup count: {len(items)}", f"Total size: {diagnostics.human_size(total)}", f"Retention: {self.settings.get('backup_retention',10)}", f"Location: {backups._backup_dir()}"])
    def choose_backup(self,title:str):
        choices=backups.legacy_list_backups(); selected={"value":None}
        items=[]
        for backup in choices: items.append((backup.label, lambda b=backup:(selected.__setitem__('value',b))))
        items.append(("Back",None))
        # Custom chooser because normal menu does not return after action.
        idx=0
        while True:
            row=self.title(title)
            if not choices: self.safe(row,2,"No backups found."); self.footer("Left: Back"); self.screen.refresh();
            else:
                for i,b in enumerate(choices): self.safe(row+i,2,("> " if i==idx else "  ")+b.label,curses.A_REVERSE|curses.A_BOLD if i==idx else 0)
                self.footer("Rotate: Move | Press: Select | Left: Back"); self.screen.refresh()
            key=self.screen.getch()
            if key==curses.KEY_UP and choices: idx=(idx-1)%len(choices)
            elif key==curses.KEY_DOWN and choices: idx=(idx+1)%len(choices)
            elif self.is_select(key) and choices: return choices[idx]
            elif self.is_back(key): return None
    def restore_backup_menu(self):
        b=self.choose_backup("Restore Backup")
        if b and self.confirm("Restore Backup?",[b.label,"Current server files will be replaced."],"Restore"): self.message("Restore Backup",["Restoring backup..."],False); self.result("Restore Backup",backups.restore(b))
    def delete_backup_menu(self):
        b=self.choose_backup("Delete Backup")
        if b and self.confirm("Delete Backup?",[b.label,"This cannot be undone."],"Delete"): self.result("Delete Backup",backups.delete(b))

    def server_settings_menu(self) -> None:
        props,err=minecraft.read_properties()
        if err: self.message("Server Settings",["Unable to read server.properties:",err]); return
        fields=[("MOTD","motd"),("Maximum Players","max-players"),("Difficulty","difficulty"),("Game Mode","gamemode"),("PvP","pvp"),("Online Mode","online-mode"),("Whitelist","white-list"),("View Distance","view-distance"),("Simulation Distance","simulation-distance")]
        self.menu("Server Settings",[(f"{label}: {props.get(key,'')}",lambda k=key,l=label:self.edit_property(l,k,props.get(k,''))) for label,key in fields]+[("Back",None)])
    def edit_property(self,label,key,current):
        value=self.text_input(label,f"New value for {key}:",current)
        if value is not None:
            result=minecraft.update_property(key,value); self.result(label,result)

    def minebox_settings_menu(self) -> None:
        restart = self.settings.get('scheduled_restart_time','') or 'Off'
        auto_backup = self.settings.get('automatic_backup_hours',0)
        self.menu("MineBox Settings",[(f"Refresh: {self.settings.get('refresh_seconds',2)} sec",self.set_refresh),(f"Temperature Unit: {self.settings.get('temperature_unit','C')}",self.toggle_temp),(f"Screen Timeout: {self.settings.get('screen_timeout_minutes',0)} min",self.set_timeout),(f"Brightness: {self.settings.get('brightness',100)}%",self.set_brightness),(f"Backup Retention: {self.settings.get('backup_retention',10)}",self.set_backup_retention),(f"Automatic Backup: {auto_backup}h" if auto_backup else "Automatic Backup: Off",self.set_auto_backup),(f"Scheduled Restart: {restart}",self.set_scheduled_restart),(f"Confirm Server Actions: {'On' if self.settings.get('confirm_server_actions',True) else 'Off'}",self.toggle_confirm_actions),("Back",None)])
    def persist_settings(self): self.result("MineBox Settings", type("R",(),{"ok":settings_service.save(self.settings)[0],"stdout":settings_service.save(self.settings)[1],"message":settings_service.save(self.settings)[1]})())
    def set_refresh(self):
        value=self.text_input("Refresh Rate","Seconds between dashboard updates:",str(self.settings.get('refresh_seconds',2)),2)
        try: self.settings['refresh_seconds']=max(1,min(60,int(value))); settings_service.save(self.settings)
        except (TypeError,ValueError): self.message("Refresh Rate",["Enter a whole number from 1 to 60."])
    def toggle_temp(self): self.settings['temperature_unit']='F' if self.settings.get('temperature_unit')=='C' else 'C'; settings_service.save(self.settings)
    def set_timeout(self):
        value=self.text_input("Screen Timeout","Minutes; 0 disables timeout:",str(self.settings.get('screen_timeout_minutes',0)),3)
        try: self.settings['screen_timeout_minutes']=max(0,min(999,int(value))); settings_service.save(self.settings)
        except (TypeError,ValueError): self.message("Screen Timeout",["Enter a whole number."])
    def set_brightness(self):
        value=self.text_input("Brightness","Brightness percentage (placeholder until display driver):",str(self.settings.get('brightness',100)),3)
        try: self.settings['brightness']=max(1,min(100,int(value))); settings_service.save(self.settings)
        except (TypeError,ValueError): self.message("Brightness",["Enter a whole number from 1 to 100."])


    def set_backup_retention(self):
        value=self.text_input("Backup Retention","Number of newest backups to keep:",str(self.settings.get('backup_retention',10)),3)
        try:
            self.settings['backup_retention']=max(1,min(999,int(value))); settings_service.save(self.settings)
        except (TypeError,ValueError): self.message("Backup Retention",["Enter a whole number from 1 to 999."])
    def toggle_confirm_actions(self):
        self.settings['confirm_server_actions']=not bool(self.settings.get('confirm_server_actions',True)); settings_service.save(self.settings)

    def set_auto_backup(self):
        value=self.text_input("Automatic Backups","Hours between backups (0 disables):",str(self.settings.get('automatic_backup_hours',0)))
        try:
            if value is not None:
                self.settings['automatic_backup_hours']=max(0,min(720,int(value))); settings_service.save(self.settings)
        except (TypeError,ValueError): self.message("Automatic Backups",["Enter a whole number from 0 to 720."])

    def set_scheduled_restart(self):
        value=self.text_input("Scheduled Restart","Daily time in 24-hour HH:MM format; blank disables:",str(self.settings.get('scheduled_restart_time','')))
        if value is None: return
        value=value.strip()
        if value:
            try:
                hour,minute=[int(x) for x in value.split(':',1)]
                if not (0 <= hour <= 23 and 0 <= minute <= 59): raise ValueError
                value=f"{hour:02d}:{minute:02d}"
            except (ValueError,TypeError):
                self.message("Scheduled Restart",["Use HH:MM, such as 04:30, or leave blank."]); return
        self.settings['scheduled_restart_time']=value; settings_service.save(self.settings)

    def toggle_quick_actions(self):
        self.settings['dashboard_quick_actions']=not bool(self.settings.get('dashboard_quick_actions',True)); settings_service.save(self.settings)

    def performance_screen(self):
        self.screen.timeout(1000)
        while True:
            sample=monitoring.sample(); hist=monitoring.history(); row=self.title("Performance")
            self.safe(row,2,f"System CPU:       {sample.cpu:5.1f}%"); row+=1
            self.safe(row,2,f"System Memory:    {sample.memory:5.1f}%"); row+=1
            self.safe(row,2,f"Minecraft Memory: {sample.server_memory_mb:5.1f} MB"); row+=2
            self.safe(row,2,"CPU history:    "+monitoring.sparkline([x.cpu for x in hist],30)); row+=1
            self.safe(row,2,"Memory history: "+monitoring.sparkline([x.memory for x in hist],30)); row+=1
            self.safe(row,2,"Each character is one recent sample.");
            self.footer("Left: Back | Right: Reset History"); self.screen.refresh(); key=self.screen.getch()
            if self.is_back(key): self.screen.timeout(-1); return
            if self.is_quick(key):
                monitoring._HISTORY.clear()

    def log_browser(self):
        level='ALL'; query=''; offset=0; self.screen.timeout(1000)
        levels=['ALL','INFO','WARN','ERROR']
        while True:
            lines=log_tools.filter_lines(level,query,1000); h,_=self.screen.getmaxyx(); available=max(3,h-7)
            shown=lines[max(0,len(lines)-available-offset):len(lines)-offset if offset else None]
            row=self.title(f"Log Browser [{level}]" + (f" Search: {query}" if query else ""))
            for line in shown[-available:]: self.safe(row,1,line); row+=1
            self.footer("Rotate: Scroll | Left: Back | Right: Log Actions"); self.screen.refresh(); key=self.screen.getch()
            if key==curses.KEY_UP: offset=min(offset+1,max(0,len(lines)-available))
            elif key==curses.KEY_DOWN: offset=max(0,offset-1)
            elif self.is_quick(key):
                action = self.choose_option("Log Actions", [f"Next Filter ({level})", "Search", "Export", "Return"])
                if action == 0: level=levels[(levels.index(level)+1)%len(levels)]; offset=0
                elif action == 1:
                    value=self.text_input("Search Logs","Text to find; blank clears:",query)
                    if value is not None: query=value; offset=0
                elif action == 2: self.result("Export Logs",log_tools.export(lines,f"{level.lower()}-logs"))
                self.screen.timeout(1000)
            elif self.is_back(key): self.screen.timeout(-1); return

    def configuration_check(self):
        rows=validation.checks(); lines=[f"{'PASS' if ok else 'FAIL'} - {name}: {detail}" for name,ok,detail in rows]
        lines += ["", f"Result: {sum(1 for _,ok,_ in rows if ok)}/{len(rows)} checks passed"]
        self.message("Configuration Check",lines)

    def worlds_software_menu(self) -> None:
        inv=diagnostics.software_inventory()
        self.menu("Worlds & Software", [("World Information",self.world_info),(f"Plugins ({len(inv['plugins'])})",lambda:self.show_inventory("Plugins",inv['plugins'])),(f"Mods ({len(inv['mods'])})",lambda:self.show_inventory("Mods",inv['mods'])),(f"Server JARs ({len(inv['jars'])})",lambda:self.show_inventory("Server JARs",inv['jars'])),("Back",None)])
    def world_info(self):
        worlds=diagnostics.world_folders()
        lines=[f"{name}: {size}" for name,size in worlds] or ["No Minecraft world folders detected."]
        self.message("World Information",lines)
    def show_inventory(self,title,items):
        self.message(title,items or [f"No {title.lower()} detected."])

    def diagnostics_menu(self) -> None:
        self.menu("Diagnostics",[("Health Summary",self.health_summary),("Configuration Check",self.configuration_check),("Network Test",self.network_test),("Storage Details",self.storage_details),("Crash Reports",self.crash_reports),("Recent Errors",self.recent_errors),("Back",None)])
    def health_summary(self):
        s=get_system_status(); lines=[f"Minecraft: {minecraft.status_text()}",f"CPU: {s['cpu']}%",f"Memory: {s['memory']}%",f"Disk: {s['disk']}%",f"Temperature: {s['temperature']}",diagnostics.latest_crash_summary()]
        self.message("Health Summary",lines)
    def network_test(self): self.message("Network Test",diagnostics.network_status())
    def storage_details(self): self.message("Storage Details",diagnostics.storage_status())
    def crash_reports(self):
        reports=diagnostics.crash_reports(); self.message("Crash Reports",[p.name for p in reports[:20]] or ["No crash reports found."])
    def recent_errors(self):
        logs=minecraft.recent_logs(500); errors=[x for x in logs if "ERROR" in x or "Exception" in x or "WARN" in x]
        self.message("Recent Errors",errors[-30:] or ["No recent warnings or errors found."])

    def system_menu(self) -> None:
        self.menu("System",[("System Information",self.system_info),("Power",self.power_menu),("Back",None)])
    def system_info(self):
        s=get_system_status(); self.message("System Information",[f"Hostname: {system_service.hostname()}",f"IP address: {s['ip_address']}",f"CPU usage: {s['cpu']}%",f"Memory usage: {s['memory']}%",f"Disk usage: {s['disk']}%",f"Temperature: {s['temperature']}",f"Uptime: {s['uptime']}"])
    def power_menu(self): self.menu("Power",[("Shutdown MineBox",self.shutdown),("Reboot MineBox",self.reboot),("Restart MineBox UI",self.restart_ui),("Back",None)])
    def shutdown(self):
        if self.confirm("Shutdown MineBox?",["Minecraft will be saved and stopped first."],"Shutdown"):
            self.message("Shutdown",["Saving and stopping Minecraft..."],False); result=minecraft.stop()
            if not result.ok: self.result("Shutdown Cancelled",result); return
            self.message("Shutdown",["Powering off..."],False); result=system_service.poweroff()
            if not result.ok: self.result("Shutdown Failed",result)
    def reboot(self):
        if self.confirm("Reboot MineBox?",["Minecraft will be saved and stopped first."],"Reboot"):
            self.message("Reboot",["Saving and stopping Minecraft..."],False); result=minecraft.stop()
            if not result.ok: self.result("Reboot Cancelled",result); return
            self.message("Reboot",["Rebooting..."],False); result=system_service.reboot()
            if not result.ok: self.result("Reboot Failed",result)
    def restart_ui(self):
        if self.confirm("Restart UI?",["Minecraft will keep running."],"Restart UI"): os.execv(sys.executable,[sys.executable]+sys.argv)
    def exit_ui(self):
        if self.confirm("Exit MineBox UI?",["Minecraft will keep running."],"Exit UI"): self.running=False
    def about(self): self.message("About MineBox",[f"MineBox OS UI {APP_VERSION}","Dedicated Minecraft server appliance.","Controls: rotary encoder, Left/Back button, and Right/Quick button."])
