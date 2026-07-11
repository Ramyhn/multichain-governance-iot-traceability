//! Minimal mock runtime for unit tests and the benchmark test suite.

use crate as pallet_supply_chain_traceability;
use core::time::Duration;
use frame_support::{
    derive_impl,
    traits::{ConstU64, UnixTime},
};
use sp_runtime::BuildStorage;

type Block = frame_system::mocking::MockBlock<Test>;

frame_support::construct_runtime!(
    pub enum Test {
        System: frame_system,
        SupplyChain: pallet_supply_chain_traceability,
    }
);

#[derive_impl(frame_system::config_preludes::TestDefaultConfig)]
impl frame_system::Config for Test {
    type Block = Block;
}

/// Fixed wall-clock so event freshness checks are deterministic in benchmarks.
pub struct MockTime;
impl UnixTime for MockTime {
    fn now() -> Duration {
        Duration::from_secs(1_000_000)
    }
}

impl pallet_supply_chain_traceability::Config for Test {
    type RuntimeEvent = RuntimeEvent;
    type TimeProvider = MockTime;
    type TimestampFreshnessWindow = ConstU64<2_000_000>;
}

pub fn new_test_ext() -> sp_io::TestExternalities {
    let mut ext: sp_io::TestExternalities = frame_system::GenesisConfig::<Test>::default()
        .build_storage()
        .unwrap()
        .into();
    // The benchmarks sign with the sp_io host crypto, which needs a keystore.
    ext.register_extension(sp_keystore::KeystoreExt(std::sync::Arc::new(
        sp_keystore::testing::MemoryKeystore::new(),
    )));
    ext
}
