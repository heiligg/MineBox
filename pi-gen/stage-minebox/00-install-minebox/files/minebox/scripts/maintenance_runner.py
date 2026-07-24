#!/usr/bin/env python3
from services.maintenance import run_once
for message in run_once():
    print(message)
