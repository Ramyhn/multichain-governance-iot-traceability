//! Runtime benchmarks for the supply-chain traceability pallet.
//!
//! Each benchmark reproduces the happy path of its extrinsic, including valid
//! Ed25519 signatures produced through the `sp_io` host crypto so the calls
//! succeed under benchmark execution. The `impl_benchmark_test_suite!` macro
//! runs every benchmark as a unit test against the mock runtime, so
//! `cargo test --features runtime-benchmarks` verifies the harness end to end.

#![cfg(feature = "runtime-benchmarks")]

use super::*;
use frame_benchmarking::v2::*;
use frame_system::RawOrigin;
use sp_core::ed25519;
use sp_std::vec;

/// Key type used only by the benchmark keystore.
const KT: sp_core::crypto::KeyTypeId = sp_core::crypto::KeyTypeId(*b"scbm");

fn zero_sig() -> ed25519::Signature {
    ed25519::Signature::from_raw([0u8; 64])
}

#[benchmarks]
mod benchmarks {
    use super::*;

    /// Onboard `device_id` under a fresh key and return that key for later signing.
    fn onboard<T: Config>(caller: &T::AccountId, device_id: &[u8]) -> ed25519::Public {
        let pubkey = sp_io::crypto::ed25519_generate(KT, None);
        let mut cred = DeviceCredential {
            device_id: device_id.to_vec(),
            public_key: pubkey,
            producer: b"producer".to_vec(),
            metadata: vec![],
            signature: zero_sig(),
        };
        let msg = Pallet::<T>::encode_credential_message(&cred);
        cred.signature = sp_io::crypto::ed25519_sign(KT, &pubkey, &msg).expect("sign");
        Pallet::<T>::onboard_device(RawOrigin::Signed(caller.clone()).into(), cred)
            .expect("onboard");
        pubkey
    }

    /// Algorithm 1: device onboarding, dominated by Ed25519 credential verification.
    #[benchmark]
    fn onboard_device() {
        let caller: T::AccountId = whitelisted_caller();
        let pubkey = sp_io::crypto::ed25519_generate(KT, None);
        let mut cred = DeviceCredential {
            device_id: b"dev-bench".to_vec(),
            public_key: pubkey,
            producer: b"producer".to_vec(),
            metadata: vec![],
            signature: zero_sig(),
        };
        let msg = Pallet::<T>::encode_credential_message(&cred);
        cred.signature = sp_io::crypto::ed25519_sign(KT, &pubkey, &msg).expect("sign");

        #[extrinsic_call]
        _(RawOrigin::Signed(caller), cred);

        assert!(Devices::<T>::contains_key(b"dev-bench".to_vec()));
    }

    /// Algorithm 2: event admission, dominated by Ed25519 event-signature verification.
    #[benchmark]
    fn process_event() {
        let caller: T::AccountId = whitelisted_caller();
        let device_id = b"dev-ingest".to_vec();
        let pubkey = onboard::<T>(&caller, &device_id);

        let mut event = IoTEvent {
            device_id: device_id.clone(),
            timestamp: 1_000_000u64,
            event_type: EventType::Temperature,
            payload: vec![1, 2, 3],
            signature: zero_sig(),
        };
        let emsg = Pallet::<T>::encode_event_message(&event);
        event.signature = sp_io::crypto::ed25519_sign(KT, &pubkey, &emsg).expect("sign");

        #[extrinsic_call]
        _(RawOrigin::Signed(caller), event);

        assert_eq!(EventCount::<T>::get(), 1);
    }

    /// Algorithm 3: governance evaluation and finite-state transition (no signature).
    #[benchmark]
    fn evaluate_governance() {
        let caller: T::AccountId = whitelisted_caller();

        #[extrinsic_call]
        _(
            RawOrigin::Signed(caller),
            b"batch-1".to_vec(),
            EventType::CustodyTransfer,
            b"Producer".to_vec(),
        );

        assert!(Batches::<T>::contains_key(b"batch-1".to_vec()));
    }

    impl_benchmark_test_suite!(Pallet, crate::mock::new_test_ext(), crate::mock::Test);
}
