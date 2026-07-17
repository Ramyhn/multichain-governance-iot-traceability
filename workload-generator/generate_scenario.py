#!/usr/bin/env python3
"""
Supply Chain Workload Generator
Generates synthetic IoT events for the agricultural traceability scenario (Section 8)

Scenario: Farm → Logistics → Retailer → Regulator
- 5 devices (3 farm sensors, 2 transport sensors)
- 1,152 sensor events over 42 hours
- Measurements: temperature, humidity, GPS; custody transfers are recorded separately
"""

import json
import hashlib
import argparse
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder
import random

OUTPUT_FILE = "agricultural_scenario_1152_events.json"
DEFAULT_SEED = 1152
DEFAULT_START_TIME = 1_700_000_000
FIVE_MINUTES_SECONDS = 300
FIFTEEN_MINUTES_SECONDS = 900
FARM_INTERVALS = 288
TRANSPORT_TEMPERATURE_INTERVALS = 216
TRANSPORT_GPS_INTERVALS = 72


@dataclass
class DeviceCredential:
    """Signed identity record used when a device is registered."""
    device_id: str
    public_key: str
    producer: str
    metadata: Dict[str, Any]
    signature: str

@dataclass
class IoTEvent:
    """Signed sensor reading emitted by a simulated IoT device."""
    device_id: str
    timestamp: int
    event_type: str
    payload: Dict[str, Any]
    signature: str


class IoTDevice:
    """Simulated IoT device with Ed25519 signing capability"""
    
    def __init__(
        self,
        device_id: str,
        device_type: str,
        location: str,
        owner: str,
        key_seed: Optional[bytes] = None,
    ):
        # Each simulated device gets a stable signing key so the paper scenario is reproducible.
        self.signing_key = SigningKey(key_seed) if key_seed else SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
        
        self.device_id = device_id
        self.device_type = device_type
        self.location = location
        self.owner = owner
        
    def get_credential(self) -> DeviceCredential:
        """Generate registration credential with proof-of-possession"""
        metadata = {
            "device_type": self.device_type,
            "location": self.location,
            "owner": self.owner,
            "capabilities": ["temperature", "humidity"] if "sensor" in self.device_type else ["gps"]
        }
        
        # The registration credential proves the device controls the private key behind its public key.
        message = f"{self.device_id}{self.verify_key.encode(HexEncoder).decode()}{self.owner}{json.dumps(metadata)}"
        signature = self.signing_key.sign(message.encode()).signature
        
        return DeviceCredential(
            device_id=self.device_id,
            public_key=self.verify_key.encode(HexEncoder).decode(),
            producer=self.owner,
            metadata=metadata,
            signature=signature.hex()
        )
    
    def generate_temperature_event(
        self,
        timestamp: int,
        rng: random.Random,
        base_temp: float = 3.5,
    ) -> IoTEvent:
        """Generate temperature measurement in Celsius."""
        # Small jitter keeps the cold-chain trace realistic without changing the expected event count.
        temperature = base_temp + rng.uniform(-0.5, 0.5)
        
        payload = {
            "temperature_celsius": round(temperature, 2),
            "sensor_id": self.device_id,
            "location": self.location
        }
        
        return self._sign_event(timestamp, "Temperature", payload)
    
    def generate_humidity_event(
        self,
        timestamp: int,
        rng: random.Random,
        base_humidity: float = 82.0,
    ) -> IoTEvent:
        """Generate humidity measurement (%)"""
        humidity = base_humidity + rng.uniform(-2.0, 2.0)
        
        payload = {
            "humidity_percent": round(humidity, 2),
            "sensor_id": self.device_id,
            "location": self.location
        }
        
        return self._sign_event(timestamp, "Humidity", payload)
    
    def generate_gps_event(self, timestamp: int, lat: float, lon: float) -> IoTEvent:
        """Generate GPS location reading"""
        payload = {
            "latitude": lat,
            "longitude": lon,
            "accuracy_meters": 5.0,
            "sensor_id": self.device_id
        }
        
        return self._sign_event(timestamp, "GPS", payload)
    
    def _sign_event(self, timestamp: int, event_type: str, payload: Dict) -> IoTEvent:
        """Sign an event exactly as the pallet will verify it."""
        message = f"{self.device_id}{timestamp}{event_type}{json.dumps(payload)}"
        signature = self.signing_key.sign(message.encode()).signature
        
        return IoTEvent(
            device_id=self.device_id,
            timestamp=timestamp,
            event_type=event_type,
            payload=payload,
            signature=signature.hex()
        )

class AgriculturalScenarioGenerator:
    """Generates the complete agricultural traceability scenario from Section 8"""
    
    def __init__(self, seed: int = DEFAULT_SEED, start_time: int = DEFAULT_START_TIME):
        self.seed = seed
        self.start_time = start_time
        self.rng = random.Random(seed)
        self.devices: List[IoTDevice] = []

    def _device_key_seed(self, device_id: str) -> bytes:
        material = f"{self.seed}:{device_id}".encode()
        return hashlib.blake2b(material, digest_size=32).digest()
        
    def setup_devices(self):
        """Create 5 devices: 3 farm sensors + 2 transport sensors"""
        # Producer-owned sensors cover cold storage and packaging before handoff.
        self.devices.append(self._make_device("farm-temp-001", "temperature_sensor", "Farm Cold Storage", "Producer"))
        self.devices.append(self._make_device("farm-temp-002", "temperature_sensor", "Farm Packaging Area", "Producer"))
        self.devices.append(self._make_device("farm-humid-001", "humidity_sensor", "Farm Cold Storage", "Producer"))
        
        # Logistics-owned sensors continue the trace during refrigerated transport.
        self.devices.append(self._make_device("truck-temp-001", "temperature_sensor", "Refrigerated Truck", "Logistics"))
        self.devices.append(self._make_device("truck-gps-001", "gps_tracker", "Refrigerated Truck", "Logistics"))
        
        print(f"✓ Created {len(self.devices)} IoT devices")

    def _make_device(self, device_id: str, device_type: str, location: str, owner: str) -> IoTDevice:
        return IoTDevice(device_id, device_type, location, owner, self._device_key_seed(device_id))
        
    def generate_credentials(self) -> List[DeviceCredential]:
        """Generate device registration credentials (Algorithm 1)"""
        credentials = [device.get_credential() for device in self.devices]
        print(f"✓ Generated {len(credentials)} device credentials with Ed25519 signatures")
        return credentials
    
    def generate_farm_phase(self) -> List[IoTEvent]:
        """
        Generate farm phase events (24 hours cold storage)
        - 288 temperature readings per sensor (2 sensors = 576 total)
        - 288 humidity readings (1 sensor)
        - Readings every 5 minutes
        """
        events = []
        
        farm_temp_sensors = self.devices[0:2]
        farm_humid_sensor = self.devices[2]
        
        for i in range(FARM_INTERVALS):
            timestamp = self.start_time + (i * FIVE_MINUTES_SECONDS)
            
            for sensor in farm_temp_sensors:
                events.append(sensor.generate_temperature_event(timestamp, self.rng, base_temp=3.4))
            
            events.append(farm_humid_sensor.generate_humidity_event(timestamp, self.rng, base_humidity=82.0))
        
        print(f"✓ Generated {len(events)} farm phase events (24 hours @ 5min intervals)")
        return events
    
    def generate_transport_phase(self) -> List[IoTEvent]:
        """
        Generate transport phase events (18 hours)
        - 216 temperature readings (5-minute intervals)
        - 72 GPS readings (15-minute intervals)
        """
        events = []
        transport_start = self.start_time + (24 * 3600)
        
        truck_temp_sensor = self.devices[3]
        truck_gps_sensor = self.devices[4]
        
        for i in range(TRANSPORT_TEMPERATURE_INTERVALS):
            timestamp = transport_start + (i * FIVE_MINUTES_SECONDS)
            events.append(truck_temp_sensor.generate_temperature_event(timestamp, self.rng, base_temp=3.8))
        
        # Simulated route from farm to retail; GPS is sampled less frequently than temperature.
        start_lat, start_lon = 37.7749, -122.4194
        end_lat, end_lon = 37.8044, -122.2712
        
        for i in range(TRANSPORT_GPS_INTERVALS):
            timestamp = transport_start + (i * FIFTEEN_MINUTES_SECONDS)
            progress = i / TRANSPORT_GPS_INTERVALS
            lat = start_lat + (end_lat - start_lat) * progress
            lon = start_lon + (end_lon - start_lon) * progress
            events.append(truck_gps_sensor.generate_gps_event(timestamp, lat, lon))
        
        print(f"✓ Generated {len(events)} transport phase events (18 hours)")
        return events
    
    def generate_custody_transfers(self) -> List[Dict[str, Any]]:
        """Generate custody transfer records"""
        transfers = [
            {
                "batch_id": "batch-lettuce-001",
                "from": "Producer",
                "to": "Logistics",
                "timestamp": self.start_time + (24 * 3600),
                "state_transition": "Packaged -> InTransit"
            },
            {
                "batch_id": "batch-lettuce-001",
                "from": "Logistics",
                "to": "Retailer",
                "timestamp": self.start_time + (42 * 3600),
                "state_transition": "InTransit -> Delivered"
            }
        ]
        print(f"✓ Generated {len(transfers)} custody transfer records")
        return transfers
    
    def generate_full_scenario(self) -> Dict[str, Any]:
        """Generate complete 1,152-event scenario"""
        self.setup_devices()
        
        scenario = {
            "metadata": {
                "scenario": "Agricultural Traceability (Section 8)",
                "total_devices": len(self.devices),
                "start_time": self.start_time,
                "seed": self.seed,
                "duration_hours": 42,
            },
            "credentials": [asdict(c) for c in self.generate_credentials()],
            "events": {
                "farm_phase": [asdict(e) for e in self.generate_farm_phase()],
                "transport_phase": [asdict(e) for e in self.generate_transport_phase()],
            },
            "custody_transfers": self.generate_custody_transfers()
        }
        
        # Custody transfers are stored separately; the event total is the 1,152 sensor readings.
        all_events = scenario["events"]["farm_phase"] + scenario["events"]["transport_phase"]
        scenario["summary"] = {
            "total_events": len(all_events),
            "farm_temperature_readings": 576,
            "farm_humidity_readings": 288,
            "transport_temperature_readings": 216,
            "transport_gps_readings": 72,
            "custody_transfers": 2,
            "breakdown": {
                "temperature": 792,
                "humidity": 288,
                "gps": 72,
                "total": 792 + 288 + 72
            }
        }
        
        print(f"\n{'='*60}")
        print(f"SCENARIO GENERATION COMPLETE")
        print(f"{'='*60}")
        print(f"Total devices: {scenario['metadata']['total_devices']}")
        print(f"Total events: {scenario['summary']['total_events']}")
        print(f"  - Temperature: {scenario['summary']['breakdown']['temperature']}")
        print(f"  - Humidity: {scenario['summary']['breakdown']['humidity']}")
        print(f"  - GPS: {scenario['summary']['breakdown']['gps']}")
        print(f"  - Custody transfers: {len(scenario['custody_transfers'])}")
        print(f"{'='*60}\n")
        
        return scenario

def hash_event(event: Dict[str, Any]) -> str:
    """Hash one event with Blake2b so the reconciliation root matches Substrate conventions."""
    event_str = json.dumps(event, sort_keys=True)
    return hashlib.blake2b(event_str.encode(), digest_size=32).hexdigest()

def build_merkle_tree(events: List[Dict[str, Any]]) -> str:
    """
    Build Merkle tree and return root hash (Algorithm 4, line 8)
    Complexity: O(n log n) for n events
    """
    if not events:
        return hashlib.blake2b(b"empty", digest_size=32).hexdigest()
    
    leaves = [hash_event(event) for event in events]
    
    current_level = leaves
    while len(current_level) > 1:
        next_level = []
        
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            
            combined = hashlib.blake2b((left + right).encode(), digest_size=32).hexdigest()
            next_level.append(combined)
        
        current_level = next_level
    
    return current_level[0]

def analyze_costs(scenario: Dict[str, Any]):
    """Compute costs based on analytical model from Section 9"""
    
    # Operational-chain fee assumptions from the paper's analytical model.
    WEIGHT_PER_REGISTRATION = 200_000
    WEIGHT_PER_EVENT = 150_000
    WEIGHT_PER_GOVERNANCE = 180_000
    
    STORAGE_PER_REGISTRATION = 256  # bytes
    STORAGE_PER_EVENT = 128  # bytes
    STORAGE_PER_GOVERNANCE = 192  # bytes
    
    FEE_PER_WEIGHT = 1e-12  # DOT per weight unit
    FEE_PER_BYTE = 1e-8  # DOT per byte
    DOT_USD = 5.0
    
    # Foundry gas report for SupplyChainAnchoring.anchorReconciliation.
    GAS_PER_ANCHOR = 275_446
    GAS_PRICE_GWEI = 0.5
    ETH_USD = 2000
    
    num_devices = len(scenario["credentials"])
    num_events = scenario["summary"]["total_events"]
    num_governance = 42
    num_custody = len(scenario["custody_transfers"])
    
    device_cost = num_devices * (WEIGHT_PER_REGISTRATION * FEE_PER_WEIGHT + 
                                  STORAGE_PER_REGISTRATION * FEE_PER_BYTE) * DOT_USD
    
    event_cost = num_events * (WEIGHT_PER_EVENT * FEE_PER_WEIGHT +
                                STORAGE_PER_EVENT * FEE_PER_BYTE) * DOT_USD
    
    governance_cost = num_governance * (WEIGHT_PER_GOVERNANCE * FEE_PER_WEIGHT +
                                        STORAGE_PER_GOVERNANCE * FEE_PER_BYTE) * DOT_USD
    
    custody_cost = num_custody * (WEIGHT_PER_GOVERNANCE * FEE_PER_WEIGHT +
                                  STORAGE_PER_GOVERNANCE * FEE_PER_BYTE) * DOT_USD
    
    operational_total = device_cost + event_cost + governance_cost + custody_cost
    
    gas_total = GAS_PER_ANCHOR
    eth_cost = (gas_total * GAS_PRICE_GWEI * 1e-9) * ETH_USD
    
    total_cost = operational_total + eth_cost
    
    print(f"\n{'='*60}")
    print(f"COST ANALYSIS (Analytical Model from Section 9)")
    print(f"{'='*60}")
    print(f"Operational Chain (Substrate):")
    print(f"  Device registrations: ${device_cost:.4f} ({num_devices} devices)")
    print(f"  Event processing: ${event_cost:.4f} ({num_events} events)")
    print(f"  Governance checkpoints: ${governance_cost:.4f} ({num_governance} checks)")
    print(f"  Custody transfers: ${custody_cost:.4f} ({num_custody} transfers)")
    print(f"  Subtotal: ${operational_total:.4f}")
    print(f"\nAnalytics Chain (Ethereum):")
    print(f"  Gas consumed: {gas_total:,} gas")
    print(f"  Gas price: {GAS_PRICE_GWEI} gwei")
    print(f"  ETH price: ${ETH_USD}")
    print(f"  Anchoring cost: ${eth_cost:.2f}")
    print(f"\nTOTAL COST: ${total_cost:.2f}")
    print(f"Per-event cost: ${total_cost/num_events:.4f}")
    print(f"{'='*60}\n")
    
    return {
        "operational": operational_total,
        "anchoring": eth_cost,
        "total": total_cost,
        "per_event": total_cost / num_events,
        "gas_consumed": gas_total
    }

def parse_args():
    parser = argparse.ArgumentParser(description="Generate the 1,152-event agricultural traceability workload.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Deterministic seed for keys and readings.")
    parser.add_argument("--start-time", type=int, default=DEFAULT_START_TIME, help="Unix timestamp for the first event.")
    parser.add_argument("--output", default=OUTPUT_FILE, help="Path to write the generated scenario JSON.")
    return parser.parse_args()

def main():
    args = parse_args()

    print("="*60)
    print("Supply Chain Workload Generator")
    print("Agricultural Traceability Scenario (Section 8)")
    print("="*60 + "\n")
    
    generator = AgriculturalScenarioGenerator(seed=args.seed, start_time=args.start_time)
    scenario = generator.generate_full_scenario()
    
    all_events = scenario["events"]["farm_phase"] + scenario["events"]["transport_phase"]
    merkle_root = build_merkle_tree(all_events)
    
    print(f"Merkle Root: {merkle_root}")
    print(f"(Ready for Algorithm 4 anchoring)")
    
    costs = analyze_costs(scenario)
    
    with open(args.output, 'w') as f:
        json.dump({
            **scenario,
            "reconciliation": {
                "merkle_root": merkle_root,
                "block_range": [1000, 1500],
                "event_count": len(all_events),
                "timestamp": args.start_time + (42 * 3600)
            },
            "cost_analysis": costs
        }, f, indent=2)
    
    print(f"\n✓ Saved complete scenario to: {args.output}")
    print(f"✓ Ready for deployment to test environment\n")

if __name__ == "__main__":
    main()
