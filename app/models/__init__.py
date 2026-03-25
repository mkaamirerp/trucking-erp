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
from app.models.broker import Broker, BrokerContact
from app.models.load import Load, LoadStop, LoadStopAction, LoadNote

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
from app.models.platform_admin import PlatformAdmin
from app.models.platform_integration import TenantIntegrationSecret
from app.models.email_mailbox import TenantEmailMailbox
from app.models.tenant_email_account import TenantEmailAccount
from app.models.email_ingestion import EmailThread, EmailMessage
from app.models.email_attachment import EmailMessageAttachment

# Payroll foundations (B6)
from app.models.payroll import PayPeriod, PayProfile, PayEntry, PayRun, PayRunItem
