/**
 * Onboarding workflow enums (match backend).
 * UI mapping: applicant "ACTION_REQUIRED" = status WAITING_ON_DRIVER;
 * applicant "Under review" = SUBMITTED | IN_REVIEW | WAITING_INTERNAL;
 * applicant never sees DRAFT; IN_PROGRESS is the editable state.
 */
export enum PersonApplicationStatus {
  DRAFT = "DRAFT",
  IN_PROGRESS = "IN_PROGRESS",
  SUBMITTED = "SUBMITTED",
  IN_REVIEW = "IN_REVIEW",
  WAITING_ON_DRIVER = "WAITING_ON_DRIVER",
  WAITING_INTERNAL = "WAITING_INTERNAL",
  APPROVED = "APPROVED",
  REJECTED = "REJECTED",
}

export enum PersonApplicationRequestStatus {
  OPEN = "OPEN",
  UPLOADED = "UPLOADED",
  ACCEPTED = "ACCEPTED",
  REJECTED = "REJECTED",
  EXPIRED = "EXPIRED",
}

export enum PersonApplicationRequestType {
  CRIMINAL_RECORD = "CRIMINAL_RECORD",
  DRUG_TEST = "DRUG_TEST",
  MVR = "MVR",
  MEDICAL_CARD = "MEDICAL_CARD",
  EMPLOYMENT_VERIFICATION = "EMPLOYMENT_VERIFICATION",
  OTHER = "OTHER",
}

export enum DocumentRequirementScopeType {
  ROLE = "ROLE",
  FORM = "FORM",
}

export enum DocumentRequirementVisibility {
  APPLICANT = "APPLICANT",
  ADMIN_ONLY = "ADMIN_ONLY",
}

export enum DocumentRequirementStage {
  SUBMIT = "SUBMIT",
  POST_SUBMIT = "POST_SUBMIT",
}
