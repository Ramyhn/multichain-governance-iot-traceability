//! Genuine connectivity / freshness measurement.
//!
//! Drives the real `process_event` admission path (schema check, freshness
//! window, device lookup, active-status, Ed25519 verification, storage) against
//! a synthetic on/off connectivity trace, and reports the fraction of readings
//! admitted within the freshness window. This is the measured counterpart to
//! the simulated connectivity figure in the paper: the admission logic really
//! executes on the pallet; only the connectivity trace is synthetic input.
//!
//! With `MockTime::now()` fixed at 1,000,000 s, a reading buffered for `delay`
//! seconds is submitted with `timestamp = 1,000,000 - delay`, so the pallet's
//! own check `now - timestamp <= window` evaluates `delay <= window`.
//!
//! Run: `cargo test connectivity_measurement -- --nocapture`

use crate::mock::{new_test_ext, Test, FRESHNESS_WINDOW, SupplyChain};
use crate::{DeviceCredential, EventType, IoTEvent};
use frame_system::RawOrigin;
use sp_core::{ed25519, Pair};
use std::sync::atomic::Ordering;

const NOW: u64 = 1_000_000; // MockTime::now() in seconds
const EMIT_INTERVAL: u64 = 300; // one signed reading every 5 minutes
const MEAN_ON: f64 = 900.0; // mean 15-minute connected period
const READINGS: usize = 1500; // readings per sweep point
const CALLER: u64 = 1;

/// Small deterministic xorshift64 RNG (avoids adding a dev-dependency).
struct Rng(u64);
impl Rng {
    fn next_u64(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.0 = x;
        x
    }
    fn unit(&mut self) -> f64 {
        ((self.next_u64() >> 11) as f64 + 1.0) / ((1u64 << 53) as f64)
    }
    fn exp(&mut self, mean: f64) -> f64 {
        -mean * self.unit().ln()
    }
}

fn onboard(pair: &ed25519::Pair, device_id: &[u8]) {
    let mut cred = DeviceCredential {
        device_id: device_id.to_vec(),
        public_key: pair.public(),
        producer: b"producer".to_vec(),
        metadata: Vec::new(),
        signature: ed25519::Signature::from_raw([0u8; 64]),
    };
    let msg = SupplyChain::encode_credential_message(&cred);
    cred.signature = pair.sign(&msg);
    SupplyChain::onboard_device(RawOrigin::Signed(CALLER).into(), cred).expect("onboard");
}

/// Emit `READINGS` readings over an on/off trace with the given mean outage, and
/// return the fraction accepted by the real `process_event` under `window` s.
fn admitted_fraction(
    pair: &ed25519::Pair,
    device_id: &[u8],
    mean_off: f64,
    window: u64,
    tag: u8,
    rng: &mut Rng,
) -> f64 {
    FRESHNESS_WINDOW.store(window, Ordering::Relaxed);
    // Keep the frame-system event buffer from growing across points.
    frame_system::Pallet::<Test>::reset_events();

    let mut state_on = true;
    let mut switch_at = rng.exp(MEAN_ON);
    let mut emit_t = 0.0f64;
    let mut admitted = 0usize;
    for i in 0..READINGS {
        while emit_t >= switch_at {
            state_on = !state_on;
            switch_at += if state_on { rng.exp(MEAN_ON) } else { rng.exp(mean_off) };
        }
        // A reading in an outage is delivered when connectivity returns.
        let delay = if state_on { 0.0 } else { switch_at - emit_t };
        let ts = NOW.saturating_sub(delay.round() as u64);

        let mut payload = Vec::with_capacity(5);
        payload.push(tag);
        payload.extend_from_slice(&(i as u32).to_le_bytes());
        let mut event = IoTEvent {
            device_id: device_id.to_vec(),
            timestamp: ts,
            event_type: EventType::Temperature,
            payload,
            signature: ed25519::Signature::from_raw([0u8; 64]),
        };
        let emsg = SupplyChain::encode_event_message(&event);
        event.signature = pair.sign(&emsg);
        if SupplyChain::process_event(RawOrigin::Signed(CALLER).into(), event).is_ok() {
            admitted += 1;
        }
        emit_t += EMIT_INTERVAL as f64;
    }
    admitted as f64 / READINGS as f64
}

#[test]
fn connectivity_measurement() {
    new_test_ext().execute_with(|| {
        let device_id = b"dev-conn".to_vec();
        let pair = ed25519::Pair::from_seed(&[7u8; 32]);
        onboard(&pair, &device_id);

        // freshness windows: 5, 15, 60 minutes (seconds, label in minutes)
        let windows: [(u64, u32); 3] = [(300, 5), (900, 15), (3600, 60)];

        println!("MEASURE_CSV_BEGIN");
        println!("MEASURE_CSV,mean_outage_min,window_min,admitted_pct");
        for (wi, &(w, wl)) in windows.iter().enumerate() {
            for step in 1..=15u64 {
                let off_min = step as f64 * 4.0; // 4..60 minutes
                let off = off_min * 60.0; // seconds
                let mut rng = Rng(
                    0x9E37_79B9_7F4A_7C15u64
                        ^ w.wrapping_mul(0x1000_0001)
                        ^ step.wrapping_mul(0x0100_0193),
                );
                let tag = ((wi as u8) << 5) | (step as u8);
                let frac = admitted_fraction(&pair, &device_id, off, w, tag, &mut rng);
                println!("MEASURE_CSV,{:.1},{},{:.2}", off_min, wl, frac * 100.0);
            }
        }
        println!("MEASURE_CSV_END");
    });
}
