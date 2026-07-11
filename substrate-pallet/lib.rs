// SPDX-License-Identifier: Apache-2.0
//! Supply Chain Traceability Pallet
//! 
//! Implements Algorithms 1-3 from the paper:
//! - Algorithm 1: Device Onboarding
//! - Algorithm 2: IoT Event Processing  
//! - Algorithm 3: Governance Evaluation

#![cfg_attr(not(feature = "std"), no_std)]

pub use pallet::*;

#[cfg(test)]
mod mock;

#[cfg(test)]
mod connectivity;

#[cfg(feature = "runtime-benchmarks")]
mod benchmarking;

#[frame_support::pallet]
pub mod pallet {
    use frame_support::{
        pallet_prelude::*,
        traits::UnixTime,
    };
    use frame_system::pallet_prelude::*;
    use sp_core::{ed25519, H256};
    use sp_runtime::traits::{BlakeTwo256, Hash};
    use sp_std::vec::Vec;
    use codec::{Encode, Decode};
    use scale_info::TypeInfo;

    // Domain types used by the traceability workflow.

    /// Device credential for onboarding (Algorithm 1)
    #[derive(Clone, Encode, Decode, Eq, PartialEq, RuntimeDebug, TypeInfo)]
    pub struct DeviceCredential {
        pub device_id: Vec<u8>,
        pub public_key: ed25519::Public,
        pub producer: Vec<u8>,
        pub metadata: Vec<u8>,
        pub signature: ed25519::Signature,
    }

    /// Registered device record
    #[derive(Clone, Encode, Decode, Eq, PartialEq, RuntimeDebug, TypeInfo)]
    pub struct DeviceRecord {
        pub device_id: Vec<u8>,
        pub public_key: ed25519::Public,
        pub producer: Vec<u8>,
        pub metadata: Vec<u8>,
        pub registered_at: u64,
        pub status: DeviceStatus,
    }

    #[derive(Clone, Encode, Decode, Eq, PartialEq, RuntimeDebug, TypeInfo)]
    pub enum DeviceStatus {
        Active,
        Suspended,
        Revoked,
    }

    /// IoT event types from the agricultural scenario
    #[derive(Clone, Encode, Decode, Eq, PartialEq, RuntimeDebug, TypeInfo)]
    pub enum EventType {
        Temperature,
        Humidity,
        GPS,
        CustodyTransfer,
        QualityInspection,
    }

    /// IoT measurement event (Algorithm 2)
    #[derive(Clone, Encode, Decode, Eq, PartialEq, RuntimeDebug, TypeInfo)]
    pub struct IoTEvent {
        pub device_id: Vec<u8>,
        pub timestamp: u64,
        pub event_type: EventType,
        pub payload: Vec<u8>, // JSON-encoded sensor data
        pub signature: ed25519::Signature,
    }

    /// Batch state for custody tracking (Algorithm 3)
    #[derive(Clone, Encode, Decode, Eq, PartialEq, RuntimeDebug, TypeInfo)]
    pub enum BatchState {
        Harvested,
        Packaged,
        InTransit,
        Delivered,
        Inspected,
    }

    /// Governance policy outcome
    #[derive(Clone, Encode, Decode, Eq, PartialEq, RuntimeDebug, TypeInfo)]
    pub enum GovernanceOutcome {
        Approved,
        Rejected,
    }

    #[pallet::pallet]
    #[pallet::without_storage_info]
    pub struct Pallet<T>(_);

    #[pallet::config]
    pub trait Config: frame_system::Config {
        type RuntimeEvent: From<Event<Self>> + IsType<<Self as frame_system::Config>::RuntimeEvent>;
        type TimeProvider: UnixTime;
        
        /// Maximum timestamp freshness window (replay attack prevention)
        #[pallet::constant]
        type TimestampFreshnessWindow: Get<u64>;
    }

    // Pallet storage indexed for device lookup, event retrieval, and batch state checks.

    /// Device registry: device_id -> DeviceRecord
    #[pallet::storage]
    #[pallet::getter(fn devices)]
    pub type Devices<T: Config> = StorageMap<_, Blake2_128Concat, Vec<u8>, DeviceRecord>;

    /// Event index: event_hash -> IoTEvent
    #[pallet::storage]
    #[pallet::getter(fn events)]
    pub type Events<T: Config> = StorageMap<_, Blake2_128Concat, H256, IoTEvent>;

    /// Event counter for metrics
    #[pallet::storage]
    #[pallet::getter(fn event_count)]
    pub type EventCount<T: Config> = StorageValue<_, u64, ValueQuery>;

    /// Device counter for metrics
    #[pallet::storage]
    #[pallet::getter(fn device_count)]
    pub type DeviceCount<T: Config> = StorageValue<_, u64, ValueQuery>;

    /// Batch state tracking: batch_id -> BatchState
    #[pallet::storage]
    #[pallet::getter(fn batches)]
    pub type Batches<T: Config> = StorageMap<_, Blake2_128Concat, Vec<u8>, BatchState>;

    /// Policy evaluation counter
    #[pallet::storage]
    #[pallet::getter(fn governance_checkpoints)]
    pub type GovernanceCheckpoints<T: Config> = StorageValue<_, u64, ValueQuery>;

    // Runtime events emitted for audit and off-chain reconciliation.

    #[pallet::event]
    #[pallet::generate_deposit(pub(super) fn deposit_event)]
    pub enum Event<T: Config> {
        /// Device registered successfully (Algorithm 1, line 17)
        DeviceRegistered {
            device_id: Vec<u8>,
            public_key: ed25519::Public,
            producer: Vec<u8>,
        },
        /// Event processed successfully (Algorithm 2, line 28)
        EventProcessed {
            device_id: Vec<u8>,
            event_hash: H256,
            event_type: EventType,
            timestamp: u64,
        },
        /// Governance evaluation completed (Algorithm 3)
        GovernanceEvaluated {
            batch_id: Vec<u8>,
            outcome: GovernanceOutcome,
            new_state: Option<BatchState>,
        },
        /// Invalid signature detected
        SignatureVerificationFailed {
            device_id: Vec<u8>,
        },
        /// Timestamp freshness check failed
        TimestampStale {
            device_id: Vec<u8>,
            event_timestamp: u64,
            current_time: u64,
        },
    }

    // Validation and governance failures surfaced by the extrinsics.

    #[pallet::error]
    pub enum Error<T> {
        /// Invalid device credential signature (Algorithm 1, line 4)
        InvalidCredentialSignature,
        /// Invalid credential schema (Algorithm 1, line 8)
        InvalidCredentialSchema,
        /// Device not found (Algorithm 2, line 13)
        DeviceNotRegistered,
        /// Invalid event signature (Algorithm 2, line 17)
        InvalidEventSignature,
        /// Stale timestamp - replay attack prevention (Algorithm 2, line 8)
        StaleTimestamp,
        /// Invalid event schema (Algorithm 2, line 4)
        InvalidEventSchema,
        /// Device already registered
        DeviceAlreadyRegistered,
        /// Policy conditions not satisfied (Algorithm 3, line 6)
        PolicyConditionsNotMet,
        /// Invalid state transition (Algorithm 3, line 10)
        InvalidStateTransition,
        /// Device is suspended or revoked, so its measurements are refused
        DeviceNotActive,
    }

    // Public extrinsics implementing onboarding, event ingestion, and policy checks.

    #[pallet::call]
    impl<T: Config> Pallet<T> {
        /// Algorithm 1: Device Onboarding Workflow
        /// 
        /// Complexity: O(n + m) where n = credential fields, m = events/block
        #[pallet::call_index(0)]
        #[pallet::weight(200_000 + 256 * 20_000)] // ~200k weight + 256 bytes storage
        pub fn onboard_device(
            origin: OriginFor<T>,
            credential: DeviceCredential,
        ) -> DispatchResult {
            ensure_signed(origin)?;

            // The device must prove control of the private key before it can be registered.
            let message = Self::encode_credential_message(&credential);
            ensure!(
                sp_io::crypto::ed25519_verify(
                    &credential.signature,
                    &message,
                    &credential.public_key
                ),
                Error::<T>::InvalidCredentialSignature
            );

            // Keep obviously malformed credentials out of storage.
            ensure!(
                Self::validate_credential_schema(&credential),
                Error::<T>::InvalidCredentialSchema
            );

            // Device IDs are stable identifiers and cannot be reused.
            ensure!(
                !Devices::<T>::contains_key(&credential.device_id),
                Error::<T>::DeviceAlreadyRegistered
            );

            let record = DeviceRecord {
                device_id: credential.device_id.clone(),
                public_key: credential.public_key,
                producer: credential.producer.clone(),
                metadata: credential.metadata,
                registered_at: T::TimeProvider::now().as_secs(),
                status: DeviceStatus::Active,
            };

            Devices::<T>::insert(&credential.device_id, record);
            DeviceCount::<T>::mutate(|count| *count += 1);

            Self::deposit_event(Event::DeviceRegistered {
                device_id: credential.device_id,
                public_key: credential.public_key,
                producer: credential.producer,
            });

            Ok(())
        }

        /// Algorithm 2: IoT Event Admission and Dispatch
        /// 
        /// Complexity: O(k + log d) where k = event fields, d = total devices
        #[pallet::call_index(1)]
        #[pallet::weight(150_000 + 128 * 20_000)] // ~150k weight + 128 bytes storage
        pub fn process_event(
            origin: OriginFor<T>,
            event: IoTEvent,
        ) -> DispatchResult {
            ensure_signed(origin)?;

            // Reject incomplete payloads before doing signature or storage work.
            ensure!(
                Self::validate_event_schema(&event),
                Error::<T>::InvalidEventSchema
            );

            // The freshness window limits replay of otherwise valid signed readings.
            let current_time = T::TimeProvider::now().as_secs();
            let freshness_window = T::TimestampFreshnessWindow::get();
            
            ensure!(
                event.timestamp <= current_time &&
                current_time - event.timestamp <= freshness_window,
                Error::<T>::StaleTimestamp
            );

            let device = Devices::<T>::get(&event.device_id)
                .ok_or(Error::<T>::DeviceNotRegistered)?;

            // Measurements from a suspended or revoked device are refused.
            ensure!(
                matches!(device.status, DeviceStatus::Active),
                Error::<T>::DeviceNotActive
            );

            // Events are accepted only if they were signed by the registered device key.
            let message = Self::encode_event_message(&event);
            ensure!(
                sp_io::crypto::ed25519_verify(
                    &event.signature,
                    &message,
                    &device.public_key
                ),
                Error::<T>::InvalidEventSignature
            );

            // The event hash is the lookup key used later by reconciliation.
            let event_hash = BlakeTwo256::hash_of(&event);
            Events::<T>::insert(event_hash, event.clone());
            EventCount::<T>::mutate(|count| *count += 1);

            Self::deposit_event(Event::EventProcessed {
                device_id: event.device_id,
                event_hash,
                event_type: event.event_type,
                timestamp: event.timestamp,
            });

            Ok(())
        }

        /// Algorithm 3: Governance Evaluation and State Transition
        /// 
        /// Complexity: O(c + log p) where c = conditions/policy, p = total policies
        #[pallet::call_index(2)]
        #[pallet::weight(180_000 + 192 * 20_000)] // ~180k weight + 192 bytes storage
        pub fn evaluate_governance(
            origin: OriginFor<T>,
            batch_id: Vec<u8>,
            event_type: EventType,
            role: Vec<u8>, // Producer, Logistics, Retailer, Regulator
        ) -> DispatchResult {
            ensure_signed(origin)?;

            let current_state = Batches::<T>::get(&batch_id)
                .unwrap_or(BatchState::Harvested);

            // The prototype keeps policy logic local and deterministic for reproducible experiments.
            let policy_outcome = Self::lookup_and_evaluate_policy(
                &event_type,
                &role,
                &current_state,
            )?;

            match policy_outcome {
                GovernanceOutcome::Approved => {
                    let next_state = Self::state_transition(&current_state, &event_type)?;
                    
                    Batches::<T>::insert(&batch_id, next_state.clone());
                    GovernanceCheckpoints::<T>::mutate(|count| *count += 1);

                    Self::deposit_event(Event::GovernanceEvaluated {
                        batch_id,
                        outcome: GovernanceOutcome::Approved,
                        new_state: Some(next_state),
                    });

                    Ok(())
                }
                GovernanceOutcome::Rejected => {
                    GovernanceCheckpoints::<T>::mutate(|count| *count += 1);

                    Self::deposit_event(Event::GovernanceEvaluated {
                        batch_id,
                        outcome: GovernanceOutcome::Rejected,
                        new_state: None,
                    });

                    Err(Error::<T>::PolicyConditionsNotMet.into())
                }
            }
        }
    }

    // Internal validation and state-machine helpers.

    impl<T: Config> Pallet<T> {
        /// Validate credential schema (Algorithm 1, line 6)
        fn validate_credential_schema(cred: &DeviceCredential) -> bool {
            !cred.device_id.is_empty() &&
            !cred.producer.is_empty() &&
            cred.metadata.len() <= 1024 // Max 1KB metadata
        }

        /// Validate event schema (Algorithm 2, line 2)
        fn validate_event_schema(event: &IoTEvent) -> bool {
            !event.device_id.is_empty() &&
            event.timestamp > 0 &&
            event.payload.len() <= 512 // Max 512 bytes payload
        }

        /// Encode credential for signature verification
        pub(crate) fn encode_credential_message(cred: &DeviceCredential) -> Vec<u8> {
            let mut msg = Vec::new();
            msg.extend_from_slice(&cred.device_id);
            msg.extend_from_slice(cred.public_key.as_ref());
            msg.extend_from_slice(&cred.producer);
            msg.extend_from_slice(&cred.metadata);
            msg
        }

        /// Encode event for signature verification
        pub(crate) fn encode_event_message(event: &IoTEvent) -> Vec<u8> {
            let mut msg = Vec::new();
            msg.extend_from_slice(&event.device_id);
            msg.extend_from_slice(&event.timestamp.encode());
            msg.extend_from_slice(&event.event_type.encode());
            msg.extend_from_slice(&event.payload);
            msg
        }

        /// Policy lookup and evaluation for the agricultural scenario.
        fn lookup_and_evaluate_policy(
            event_type: &EventType,
            role: &[u8],
            _state: &BatchState,
        ) -> Result<GovernanceOutcome, DispatchError> {
            // Custody movement is restricted to supply-chain actors; inspection is regulator-only.
            match event_type {
                EventType::CustodyTransfer => {
                    if role == b"Producer" || role == b"Logistics" || role == b"Retailer" {
                        Ok(GovernanceOutcome::Approved)
                    } else {
                        Ok(GovernanceOutcome::Rejected)
                    }
                }
                EventType::QualityInspection => {
                    if role == b"Regulator" {
                        Ok(GovernanceOutcome::Approved)
                    } else {
                        Ok(GovernanceOutcome::Rejected)
                    }
                }
                _ => Ok(GovernanceOutcome::Approved), // Temperature/humidity/GPS always approved
            }
        }

        /// Finite state machine transition (Algorithm 3, lines 9-12)
        fn state_transition(
            current: &BatchState,
            event_type: &EventType,
        ) -> Result<BatchState, DispatchError> {
            match (current, event_type) {
                (BatchState::Harvested, EventType::CustodyTransfer) => Ok(BatchState::Packaged),
                (BatchState::Packaged, EventType::CustodyTransfer) => Ok(BatchState::InTransit),
                (BatchState::InTransit, EventType::CustodyTransfer) => Ok(BatchState::Delivered),
                (BatchState::Delivered, EventType::QualityInspection) => Ok(BatchState::Inspected),
                _ => Err(Error::<T>::InvalidStateTransition.into()),
            }
        }
    }
}
