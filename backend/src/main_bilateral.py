"""
main_bilateral.py

Complete bilateral gait analysis system with calibration, real-time processing,
and comprehensive gait symmetry analysis.
"""

import asyncio
import json
import websockets
from collections import deque
import numpy as np
import time
import os
import sys
from bilateral_imu_joint_angle import BilateralIMUJointAngle
from bilateral_processors import (
    compute_bilateral_metrics,
    generate_bilateral_gait_report
)

# Configuration
ESP1_IP = "ws://10.134.209.36:81"  # Left leg
ESP2_IP = "ws://10.134.209.76:81"  # Right leg
MAX_SYNC_DIFF = 5  # ms
SAMPLING_RATE = 10.0  # Hz
DATA_DIR = "bilateral_data"
os.makedirs(DATA_DIR, exist_ok=True)

# Global buffers
buf_esp1 = deque(maxlen=5)
buf_esp2 = deque(maxlen=5)
synchronized_packets = []
joint_system = None


async def reader(name, uri, buffer):
    """WebSocket reader for ESP32."""
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"[{name}] Connected.")
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if "t" in data:
                        buffer.append(data)
        except Exception as e:
            print(f"[{name}] Error: {e}. Reconnecting...")
            await asyncio.sleep(1)


async def sync_processor(duration_s=30):
    """Synchronize and process data from both legs."""
    global synchronized_packets
    
    last_synced_t = None
    start_time = None
    last_status_time = time.time()

    
    while True:
        # Check duration
        if start_time and (time.time() - start_time) > duration_s:
            print(f"\n✓ Collection complete! {len(synchronized_packets)} packets")
            return
        
        # Wait for data
        if not buf_esp1 or not buf_esp2:

            await asyncio.sleep(0.001)
            continue
        
        p1 = buf_esp1[0]
        p2 = buf_esp2[0]
        t1 = p1["t"]
        t2 = p2["t"]
        
        # Synchronize by timestamp
        if abs(t1 - t2) <= MAX_SYNC_DIFF:
            if start_time is None:
                start_time = time.time()
                print("Started data collection...")
            
            if last_synced_t != min(t1, t2):
                last_synced_t = min(t1, t2)
                
                # Create synchronized packet
                synced = {
                    "timestamp": min(t1, t2),
                    "left_leg": {"thigh": p1["IMU1"], "shank": p1["IMU2"]},
                    "right_leg": {"thigh": p2["IMU1"], "shank": p2["IMU2"]}
                }
                synchronized_packets.append(synced)

                
                # Real-time angle calculation if calibrated
                if joint_system:
                    angles = joint_system.calculate_bilateral_angles(synced)
                    if angles['left_angle_deg'] and angles['right_angle_deg']:
                        # Print status every second
                        if time.time() - last_status_time >= 1.0:
                            elapsed = time.time() - start_time
                            print(f"[{elapsed:.1f}s] L: {angles['left_angle_deg']:.1f}° | "
                                  f"R: {angles['right_angle_deg']:.1f}° | "
                                  f"Diff: {angles['angle_difference_deg']:.1f}°")
                            last_status_time = time.time()
            
            buf_esp1.popleft()
            buf_esp2.popleft()
        else:
            # Remove older packet
            if t1 < t2:
                buf_esp1.popleft()
            else:
                buf_esp2.popleft()
        
        await asyncio.sleep(0.001)


async def calibration_phase(duration_s=10):
    """Collect calibration data."""
    global synchronized_packets
    synchronized_packets = []
    
    print("\n=== CALIBRATION PHASE ===")
    print(f"Move both legs through full range of motion for {duration_s} seconds...")
    
    await sync_processor(duration_s)
    
    if len(synchronized_packets) < 50:
        print("Not enough calibration data!")
        return False
        
    left_thigh  = [p["left_leg"]["thigh"]  for p in synchronized_packets if "left_leg" in p]
    left_shank  = [p["left_leg"]["shank"]  for p in synchronized_packets if "left_leg" in p]
    right_thigh = [p["right_leg"]["thigh"] for p in synchronized_packets if "right_leg" in p]
    right_shank = [p["right_leg"]["shank"] for p in synchronized_packets if "right_leg" in p]

    
    # Calibrate
    global joint_system
    joint_system = BilateralIMUJointAngle(
        delta_t=1.0/SAMPLING_RATE,
        alpha=0.92,
        adaptive_alpha=True,
        output_smooth_alpha=0.12,
        persist_path_left=os.path.join(DATA_DIR, "calib_left.npz"),
        persist_path_right=os.path.join(DATA_DIR, "calib_right.npz"),
        debug=True
    )
    
    left_ok, right_ok = joint_system.calibrate_both_legs(
        left_thigh, left_shank, right_thigh, right_shank, n_restarts=5
    )
    
    if not (left_ok and right_ok):
        print("Calibration failed!")
        return False
    
    # Save calibration
    joint_system.save_bilateral_calibration()
    print("✓ Calibration complete and saved!")
    
    return True


async def zeroing_phase(duration_s=5):
    """Set zero reference position."""
    global synchronized_packets, joint_system
    synchronized_packets = []
    
    print("\n=== ZEROING PHASE ===")
    print(f"Stand still with both legs straight for {duration_s} seconds...")
    
    await sync_processor(duration_s)
    
    if len(synchronized_packets) < 20:
        print("Not enough zeroing data!")
        return False
    
    # Use last 50 packets for zeroing
    zero_packets = synchronized_packets[-50:]
    left_thigh  = [p["left_leg"]["thigh"]  for p in zero_packets if "left_leg" in p]
    left_shank  = [p["left_leg"]["shank"]  for p in zero_packets if "left_leg" in p]
    right_thigh = [p["right_leg"]["thigh"] for p in zero_packets if "right_leg" in p]
    right_shank = [p["right_leg"]["shank"] for p in zero_packets if "right_leg" in p]

    
    try:
        joint_system.set_bilateral_zero_reference(
            left_thigh, left_shank, right_thigh, right_shank,
            gyro_thresh=0.5, use_median=True
        )
        
        # Re-estimate gyro bias
        joint_system.reestimate_bilateral_gyro_bias(
            left_thigh, left_shank, right_thigh, right_shank
        )
        
        # Save updated calibration
        joint_system.save_bilateral_calibration()
        print("✓ Zero reference set!")
        
        return True
    except Exception as e:
        print(f"Zeroing failed: {e}")
        return False


async def measurement_phase(duration_s=30):
    """Main measurement phase."""
    global synchronized_packets, joint_system
    synchronized_packets = []
    
    print("\n=== MEASUREMENT PHASE ===")
    print(f"Recording bilateral gait for {duration_s} seconds...")
    print("Walk normally with both legs...")
    
    await sync_processor(duration_s)
    
    if not synchronized_packets:
        print("No data collected!")
        return
    
    print(f"\n✓ Collected {len(synchronized_packets)} synchronized packets")
    
    # Process gait metrics
    print("\nProcessing bilateral gait metrics...")
    metrics = compute_bilateral_metrics(
        synchronized_packets,
        sampling_rate=SAMPLING_RATE
    )
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    
    # Generate report
    report = generate_bilateral_gait_report(metrics)
    with open(os.path.join(DATA_DIR, f"bilateral_gait_report_{timestamp}.json"), 'w') as f:
        json.dump(report, f, indent=2)
    
    # Save data
    
    
    # Save raw data
    raw_file = os.path.join(DATA_DIR, f"bilateral_raw_{timestamp}.json")
    with open(raw_file, 'w') as f:
        json.dump({
            'packets': synchronized_packets,
            'sampling_rate': SAMPLING_RATE,
            'duration': duration_s
        }, f)
    print(f"\n✓ Raw data saved to: {raw_file}")
    
    # Save metrics
    metrics_file = os.path.join(DATA_DIR, f"bilateral_metrics_{timestamp}.json")
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"✓ Metrics saved to: {metrics_file}")
    
    # Save CSV for analysis
    csv_file = os.path.join(DATA_DIR, f"bilateral_angles_{timestamp}.csv")
    with open(csv_file, 'w') as f:
        f.write("time_s,left_knee_deg,right_knee_deg,difference_deg\n")
        
        for i, packet in enumerate(synchronized_packets):
            t = i / SAMPLING_RATE
            angles = joint_system.calculate_bilateral_angles(packet)
            left = angles['left_angle_deg'] or 0
            right = angles['right_angle_deg'] or 0
            diff = angles['angle_difference_deg'] or 0
            f.write(f"{t:.3f},{left:.2f},{right:.2f},{diff:.2f}\n")
    
    print(f"✓ Angle data saved to: {csv_file}")
    
    # Display symmetry summary
    if 'symmetry' in metrics:
        sym = metrics['symmetry']
        print("\n" + "=" * 70)
        print("GAIT SYMMETRY SUMMARY")
        print("=" * 70)
        
        if sym.get('overall_symmetry_index'):
            print(f"Overall Symmetry: {sym['symmetry_category']}")
            print(f"Symmetry Index: {sym['overall_symmetry_index']:.1f}%")
            print("\nDetailed Symmetry Indices:")
            
            indices = [
                ('Step Time', sym.get('step_time_symmetry_index')),
                ('Stance Time', sym.get('stance_time_symmetry_index')),
                ('Swing Time', sym.get('swing_time_symmetry_index')),
                ('ROM', sym.get('rom_symmetry_index'))
            ]
            
            for name, value in indices:
                if value is not None:
                    quality = "Excellent" if value < 10 else \
                             "Good" if value < 20 else \
                             "Fair" if value < 30 else "Poor"
                    print(f"  {name:12}: {value:5.1f}% ({quality})")


async def countdown(seconds, label):
    for i in range(seconds, 0, -1):
        print(f"{label} starting in {i}...", end="\r")
        await asyncio.sleep(1)
    print(" " * 50, end="\r")  # Clear line


async def main():
    """Automated execution flow with timed gaps and clear status messages."""
    print("=" * 70)
    print("BILATERAL GAIT ANALYSIS SYSTEM (AUTO MODE)")
    print("=" * 70)
    print(f"Left Leg:  {ESP1_IP}")
    print(f"Right Leg: {ESP2_IP}")
    print(f"Sampling Rate: {SAMPLING_RATE} Hz")
    print("=" * 70)

    # Start WebSocket readers
    t1 = asyncio.create_task(reader("ESP1", ESP1_IP, buf_esp1))
    t2 = asyncio.create_task(reader("ESP2", ESP2_IP, buf_esp2))

    global joint_system

    try:
        # --- GAP BEFORE CALIBRATION ---
        print("\nPreparing for calibration...")
        await countdown(5, "Calibration")

        print("\n=== AUTO: NEW CALIBRATION (10s) ===")
        success = await calibration_phase(10)
        if not success:
            print("Calibration failed! Exiting.")
            return

        # --- GAP BEFORE ZEROING ---
        print("\nCalibration complete.")
        print("Preparing for zeroing...")
        await countdown(5, "Zeroing")

        print("\n=== AUTO: ZEROING (5s) ===")
        success = await zeroing_phase(5)
        if not success:
            print("Zeroing failed! Continuing anyway...")

        # --- GAP BEFORE MEASUREMENT ---
        print("\nZeroing complete.")
        print("Preparing for measurement...")
        await countdown(10, "Measurement")

        print("\n=== AUTO: STARTING MEASUREMENT (30s) ===")
        await measurement_phase(30)

        print("\n=== AUTO MODE COMPLETE ===")

    except KeyboardInterrupt:
        print("\nProgram terminated by user.")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cancel WebSocket reader tasks safely
        t1.cancel()
        t2.cancel()
        try:
            await t1
            await t2
        except:
            pass


if __name__ == "__main__":
    # Expecting: python main_bilateral.py <patient_id> <patient_name>
    if len(sys.argv) < 3:
        print("Missing patient_id / patient_name")
        sys.exit(1)

    PATIENT_ID = sys.argv[1]
    PATIENT_NAME = sys.argv[2]

    # Create directory: backend/data/recordings/patient_name/date-time/
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    BASE_RECORD_DIR = os.path.join("data", "recordings", PATIENT_NAME, timestamp)
    os.makedirs(BASE_RECORD_DIR, exist_ok=True)

    # Override data dir for this run
    DATA_DIR = BASE_RECORD_DIR

    asyncio.run(main())