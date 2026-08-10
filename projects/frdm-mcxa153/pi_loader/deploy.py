#!/usr/bin/env python3
"""
Compile a small C extension and load + run it on a FRDM-MCXA153 board
over its MCU-Link serial console, using Zephyr's LLEXT shell. No
reflashing involved -- the board must already be running llext_min
(or any image with CONFIG_LLEXT_SHELL=y).

Usage:
    python3 deploy.py <source.c> <extension_name> <function_to_call> \
        [--port /dev/ttyACM0] [--baud 115200] [--gcc arm-zephyr-eabi-gcc]
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time

import serial

CPU_FLAGS = ["-mcpu=cortex-m33+nodsp", "-mthumb", "-mabi=aapcs", "-mlong-calls"]


def compile_extension(src_path, gcc):
    out_path = tempfile.mktemp(suffix=".llext")
    cmd = [gcc, *CPU_FLAGS, "-c", "-o", out_path, src_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Compile failed:\n" + result.stderr, file=sys.stderr)
        sys.exit(1)
    return out_path


def read_response(ser, quiet_for=0.5, max_wait=5.0):
    """Read until the serial line has been quiet for `quiet_for` seconds."""
    ser.timeout = 0.1
    buf = b""
    deadline = time.time() + max_wait
    last_data = time.time()
    while time.time() < deadline:
        chunk = ser.read(4096)
        if chunk:
            buf += chunk
            last_data = time.time()
        elif time.time() - last_data > quiet_for:
            break
    return buf.decode(errors="replace")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", help="Path to the extension's .c file")
    ap.add_argument("name", help="Name to load the extension as")
    ap.add_argument("function", help="Function inside the extension to call")
    ap.add_argument("--port", default="/dev/ttyACM0", help="Serial device")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--gcc", default="arm-zephyr-eabi-gcc",
                     help="Cross-compiler; must match the board's arch/ABI")
    args = ap.parse_args()

    print(f"[1/4] Compiling {args.source} ...")
    obj_path = compile_extension(args.source, args.gcc)
    size = os.path.getsize(obj_path)
    print(f"      -> {size} bytes")

    with open(obj_path, "rb") as f:
        hex_str = f.read().hex()
    os.remove(obj_path)

    print(f"[2/4] Opening {args.port} @ {args.baud} baud ...")
    with serial.Serial(args.port, args.baud, timeout=0.2) as ser:
        # Opening the port toggles DTR on the MCU-Link's virtual COM port,
        # which resets the target. Give it time to finish booting.
        time.sleep(2.0)
        ser.reset_input_buffer()

        # This board's RAM is tight enough that only one extension fits
        # comfortably at a time -- drop any previous copy of this name first.
        ser.write(f"llext unload {args.name}\r\n".encode())
        read_response(ser, max_wait=1.5)

        print(f"[3/4] Loading '{args.name}' ({len(hex_str)} hex chars) ...")
        ser.write(f"llext load_hex {args.name} {hex_str}\r\n".encode())
        resp = read_response(ser, max_wait=8.0)
        if "Successfully loaded" not in resp:
            print("Aborting: extension did not load. Full response:\n" + resp,
                  file=sys.stderr)
            sys.exit(1)
        print("      Successfully loaded")

        print(f"[4/4] Calling {args.name}.{args.function}() ...")
        ser.write(f"llext call_fn {args.name} {args.function}\r\n".encode())
        resp = read_response(ser)
        # Strip the echoed command itself and the shell prompt noise.
        lines = [l for l in resp.splitlines()
                 if l.strip() and "call_fn" not in l and "uart:~$" not in l]
        print("      output: " + (" / ".join(lines) if lines else "(none)"))


if __name__ == "__main__":
    main()
