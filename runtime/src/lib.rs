//! Minimal runtime that wraps `pallet-supply-chain-traceability` so that
//! `frame-omni-bencher` can execute the pallet's benchmarks against a real
//! WASM runtime and produce measured weights.
//!
//! The runtime contains only `frame-system` and the traceability pallet. The
//! time provider returns a fixed wall-clock, matching the mock runtime used by
//! the benchmark test suite, so the benchmark setup code (which signs events
//! with `timestamp = 1_000_000`) admits events deterministically.

#![cfg_attr(not(feature = "std"), no_std)]

extern crate alloc;

#[cfg(feature = "std")]
include!(concat!(env!("OUT_DIR"), "/wasm_binary.rs"));

use alloc::vec::Vec;
use core::time::Duration;
use frame_support::{
    construct_runtime, derive_impl,
    traits::{ConstU64, UnixTime},
};
use sp_runtime::{create_runtime_str, generic, traits::BlakeTwo256};
use sp_version::RuntimeVersion;

pub type BlockNumber = u32;
pub type Signature = sp_runtime::MultiSignature;
pub type AccountId = sp_runtime::AccountId32;
pub type Address = sp_runtime::MultiAddress<AccountId, ()>;
pub type Header = generic::Header<BlockNumber, BlakeTwo256>;
pub type Block = generic::Block<Header, UncheckedExtrinsic>;
pub type UncheckedExtrinsic = generic::UncheckedExtrinsic<Address, RuntimeCall, Signature, ()>;

#[sp_version::runtime_version]
pub const VERSION: RuntimeVersion = RuntimeVersion {
    spec_name: create_runtime_str!("traceability-runtime"),
    impl_name: create_runtime_str!("traceability-runtime"),
    authoring_version: 1,
    spec_version: 1,
    impl_version: 1,
    apis: RUNTIME_API_VERSIONS,
    transaction_version: 1,
    system_version: 1,
};

construct_runtime!(
    pub enum Runtime {
        System: frame_system,
        SupplyChain: pallet_supply_chain_traceability,
    }
);

#[derive_impl(frame_system::config_preludes::SolochainDefaultConfig)]
impl frame_system::Config for Runtime {
    type Block = Block;
    type Version = Version;
}

/// Fixed wall-clock matching the benchmark test suite's mock runtime.
pub struct BenchTime;
impl UnixTime for BenchTime {
    fn now() -> Duration {
        Duration::from_secs(1_000_000)
    }
}

impl pallet_supply_chain_traceability::Config for Runtime {
    type RuntimeEvent = RuntimeEvent;
    type TimeProvider = BenchTime;
    type TimestampFreshnessWindow = ConstU64<2_000_000>;
}

#[cfg(feature = "runtime-benchmarks")]
frame_benchmarking::define_benchmarks!(
    [pallet_supply_chain_traceability, SupplyChain]
);

pub struct Version;
impl frame_support::traits::Get<RuntimeVersion> for Version {
    fn get() -> RuntimeVersion {
        VERSION
    }
}

sp_api::impl_runtime_apis! {
    impl sp_api::Core<Block> for Runtime {
        fn version() -> RuntimeVersion {
            VERSION
        }

        fn execute_block(_block: Block) {
            unimplemented!("benchmark-only runtime")
        }

        fn initialize_block(
            _header: &Header,
        ) -> sp_runtime::ExtrinsicInclusionMode {
            sp_runtime::ExtrinsicInclusionMode::AllExtrinsics
        }
    }

    impl sp_api::Metadata<Block> for Runtime {
        fn metadata() -> sp_core::OpaqueMetadata {
            sp_core::OpaqueMetadata::new(Runtime::metadata().into())
        }

        fn metadata_at_version(version: u32) -> Option<sp_core::OpaqueMetadata> {
            Runtime::metadata_at_version(version)
        }

        fn metadata_versions() -> Vec<u32> {
            Runtime::metadata_versions()
        }
    }

    impl sp_genesis_builder::GenesisBuilder<Block> for Runtime {
        fn build_state(config: Vec<u8>) -> sp_genesis_builder::Result {
            frame_support::genesis_builder_helper::build_state::<RuntimeGenesisConfig>(config)
        }

        fn get_preset(id: &Option<sp_genesis_builder::PresetId>) -> Option<Vec<u8>> {
            frame_support::genesis_builder_helper::get_preset::<RuntimeGenesisConfig>(id, |_| None)
        }

        fn preset_names() -> Vec<sp_genesis_builder::PresetId> {
            Vec::new()
        }
    }

    #[cfg(feature = "runtime-benchmarks")]
    impl frame_benchmarking::Benchmark<Block> for Runtime {
        fn benchmark_metadata(extra: bool) -> (
            Vec<frame_benchmarking::BenchmarkList>,
            Vec<frame_support::traits::StorageInfo>,
        ) {
            use frame_benchmarking::{Benchmarking, BenchmarkList};
            use frame_support::traits::StorageInfoTrait;

            let mut list = Vec::<BenchmarkList>::new();
            list_benchmarks!(list, extra);
            let storage_info = AllPalletsWithSystem::storage_info();
            (list, storage_info)
        }

        fn dispatch_benchmark(
            config: frame_benchmarking::BenchmarkConfig,
        ) -> Result<Vec<frame_benchmarking::BenchmarkBatch>, alloc::string::String> {
            use frame_benchmarking::{Benchmarking, BenchmarkBatch};
            use frame_support::traits::{TrackedStorageKey, WhitelistedStorageKeys};

            let whitelist: Vec<TrackedStorageKey> =
                AllPalletsWithSystem::whitelisted_storage_keys();
            let mut batches = Vec::<BenchmarkBatch>::new();
            let params = (&config, &whitelist);
            add_benchmarks!(params, batches);
            Ok(batches)
        }
    }
}
