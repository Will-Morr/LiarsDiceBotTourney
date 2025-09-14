#!/usr/bin/env python3
"""
Simple Process Manager - Randomly kills and restarts programs every 30 seconds
"""

import subprocess
import time
import random
import signal
import sys
import os
import argparse

programs = [
    "python3 client/run_client.py localhost testBots/random.py",
    "python3 client/run_client.py localhost testBots/singleRaise.py",
    "python3 client/run_client.py localhost testBots/call.py",
    "python3 client/run_client.py localhost testBots/raise_5_sixes.py",
    "python3 client/run_client.py localhost testBots/bidOnes.py",
]

# Dictionary to track processes {program: process_object or None}
processes = {program: None for program in programs}
running = True


parser = argparse.ArgumentParser()
parser.add_argument("-s", "--start-and-stop", action='store_true', help="Start and stop threads rather than just run them all")
args = parser.parse_args()

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    global running
    print(f"\nShutting down...")
    running = False
    kill_all()
    sys.exit(0)

def is_alive(program):
    """Check if a process is still running"""
    process = processes[program]
    if process is None:
        return False
    if process.poll() is None:
        return True
    else:
        processes[program] = None  # Mark as dead
        return False

def start_process(program):
    """Start a process"""
    try:
        print(f"Starting: {program}")
        processes[program] = subprocess.Popen(program, 
                                            shell=True, 
                                            start_new_session=True,
                                            stdout=subprocess.PIPE, 
                                            stderr=subprocess.PIPE,
                                            )
    except Exception as e:
        print(f"Failed to start {program}: {e}")

def kill_process(program):
    """Kill a process"""
    print(f"Killing: {program}")
    process = processes[program]
    if process:
        os.killpg(process.pid, signal.SIGTERM)
        processes[program] = None

    # if process and process.poll() is None:
    #     try:
    #         print(f"Killing: {program}")
    #         process.terminate()
    #         process.wait(timeout=1)
    #     except subprocess.TimeoutExpired:
    #         process.kill()
    #     except Exception as e:
    #         print(f"Failed to kill {program}: {e}")
    #     finally:
    #         processes[program] = None

def kill_all():
    """Kill all running processes"""
    for program in programs:
        kill_process(program)

def get_live_dead():
    """Get lists of live and dead processes"""
    live = [p for p in programs if is_alive(p)]
    dead = [p for p in programs if not is_alive(p)]
    print(f"live:{live}")
    print(f"dead:{dead}")
    return live, dead

def cycle_processes():
    """Kill 3 random live processes and start 3 random dead processes"""
    live, dead = get_live_dead()
    
    print(f"\n--- Cycle Update ---")
    
    # Kill up to 3 random live processes
    maxKill = len(live) - 3
    if maxKill < 0:
        maxKill = 0
    
    minKill = min(2, maxKill)

    if live:
        to_kill = random.sample(live, min(random.randint(minKill, maxKill), len(live)))
        for program in to_kill:
            kill_process(program)
    
    # Start up to 3 random dead processes
    if dead:
        to_start = random.sample(dead, min(random.randint(0, 3), len(dead)))
        for program in to_start:
            start_process(program)

    print(f"Live: {len(live)}, Dead: {len(dead)}")

# Set up signal handler
signal.signal(signal.SIGINT, signal_handler)

# Main loop
print("Starting Process Manager (Ctrl+C to stop)")

if args.start_and_stop:
    try:
        print("Initial cycling")
        cycle_processes()
        while running:
            time.sleep(30)  # Wait 30 seconds
            if running:
                cycle_processes()
    except KeyboardInterrupt:
        pass
    finally:
        kill_all()
else:
    for process in processes:
        start_process(process)
    while True:
        time.sleep(1)