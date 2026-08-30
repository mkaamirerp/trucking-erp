from app.models.base import Base

from app.models.driver import Driver
from app.models.driver_phone import DriverPhone
from app.models.truck import Truck
from app.models.trailer import Trailer
from app.models.fleet_document import FleetDocument

from app.models.driver_document import DriverDocument
from app.models.driver_document_file import DriverDocumentFile
from app.models.driver_onboarding_submission import DriverOnboardingSubmission
from app.models.person import Person, PersonRole, DriverProfile
from app.models.driver_person_extension import DriverPersonExtension
from app.models.tenant_auth import TenantUser, TenantUserInvite, TenantWorkspaceMember
from app.models.payee import (
    Payee,
    CompensationProfile,
    TenantMileagePolicy,
    ChargeCategory,
    CompProfileChargeRule,
    EscrowAccount,
    EscrowRule,
    EscrowLedgerEntry,
    PayeeBalance,
    PayRunOverride,
    PayDocument,
    PayoutRail,
    TenantPayoutRailSetting,
    PayeePayoutPreference,
    PayRunPayment,
    TenantBankConnector,
)
from app.models.broker import Broker, BrokerAlias, BrokerContact, BrokerDomain, BrokerKnownSender
from app.models.customs_broker import CustomsBroker, CustomsBrokerContact, LoadCustomsSnapshot
from app.models.load import Load, LoadStop, LoadStopAction, LoadNote
from app.models.load_custody_event import LoadCustodyEvent
from app.models.terminal import Terminal
from app.models.load_lab import LoadLabExtractionRun, LoadLabPromoteAudit
from app.models.extraction_field_learning import ExtractionFieldLearningEvent
from app.models.platform_extraction_learning import PlatformExtractionSanitizedPattern
from app.models.dispatch_trip import TenantDispatchNumbering, DispatchTrip
from app.models.trip import Trip, TripLoad

# Platform models (B3 onboarding)
from app.models.platform import (
    PlatformTenant,
    PlatformUser,
    PlatformTenantMember,
    PlatformSubscription,
    PlatformOTPToken,
    PlatformSecurityEvent,
    PlatformCompanyProfile,
    PlatformOnboardingPayload,
    ReservedSlug,
)
from app.models.global_booking_broker import (
    GlobalBookingBroker,
    GlobalBookingBrokerAlias,
    GlobalBookingBrokerAuditEvent,
    GlobalBookingBrokerDomain,
    GlobalBookingBrokerDuplicateCandidate,
    GlobalBookingBrokerKnownSender,
    GlobalBookingBrokerMergePreview,
)
from app.models.platform_admin import PlatformAdmin
from app.models.platform_integration import TenantIntegrationSecret
from app.models.email_mailbox import TenantEmailMailbox
from app.models.tenant_email_account import TenantEmailAccount
from app.models.email_ingestion import EmailThread, EmailMessage
from app.models.email_intake_review import EmailIntakeReview, EmailIntakeReviewEvent
from app.models.email_attachment import EmailMessageAttachment
from app.models.email_intake_qr_extraction import EmailIntakeQrExtraction
from app.models.domain_event_outbox import DomainEventOutbox

# Payroll foundations (B6)
from app.models.payroll import PayPeriod, PayProfile, PayEntry, PayRun, PayRunItem
