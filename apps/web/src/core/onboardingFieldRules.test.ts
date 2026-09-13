import { describe, expect, it } from "vitest";
import {
  blurNormalize,
  formatDateAsTyped,
  formatPostalCALive,
  isAgeAtLeast18,
  isCompleteIsoDate,
  isValidEmail,
  isValidNanpPhone,
  isValidPostalCA,
  isValidZipUS,
  liveNormalize,
  normalizeEmail,
  normalizeForm,
  normalizePhoneStored,
  parseNanpDigits,
  validateStep0,
  validateStep1,
  validateStep2,
  validateStep3,
  validateSubmit,
  validateOnboardingStep,
  validateNonDriverContact,
  displayPhone,
  type OnboardingSnapshot,
} from "./onboardingFieldRules";

const TODAY = new Date("2026-09-13T12:00:00");

function baseForm(over: Record<string, string> = {}): Record<string, string> {
  return {
    first_name: "Jane",
    middle_name: "",
    last_name: "Doe",
    date_of_birth: "1981-06-18",
    ssn: "",
    nationality: "",
    email: "jane@example.com",
    phone: "4165551212",
    address_street: "123 Main St",
    address_city: "Kitchener",
    address_region: "ON",
    address_postal: "N2R 0N4",
    zip_code: "",
    address_country: "CA",
    driver_license_number: "K35875601690112",
    license_region: "ON",
    license_expiry: "2031-01-12",
    license_issue_date: "2026-01-08",
    cdl_class: "AC",
    endorsements: "",
    restrictions: "",
    conditions: "",
    sex: "F",
    height: "165 cm",
    years_experience: "",
    total_miles: "",
    equipment_types: "",
    accidents_last_3_years: "",
    violations_last_3_years: "",
    dot_medical_card_expiry: "",
    emergency_contact_name: "",
    emergency_contact_relationship: "",
    emergency_contact_phone: "",
    ...over,
  };
}

function job(over: Record<string, string> = {}) {
  return {
    company_name: "Acme",
    position_title: "Driver",
    start_date: "2020-01-01",
    end_date: "",
    reason_for_leaving: "",
    supervisor_name: "",
    supervisor_phone: "",
    equipment_operated: "",
    city_state: "",
    subject_to_fmcsa: "",
    ...over,
  };
}

function ref(over: Record<string, string> = {}) {
  return {
    full_name: "Alex Smith",
    relationship: "",
    company: "",
    phone: "4165551212",
    email: "",
    known_duration: "",
    ...over,
  };
}

function snap(over: Partial<OnboardingSnapshot> = {}): OnboardingSnapshot {
  return {
    form: baseForm(),
    jobs: [job()],
    refs: [ref(), ref({ full_name: "Pat Lee", email: "pat@co.com", phone: "" })],
    dlFrontConfirmed: true,
    dlBackConfirmed: true,
    documents: { dot_medical: "a.pdf", mvr: "b.pdf", drug_test: "c.pdf", psp_report: "d.pdf" },
    agreeInfoAccurate: true,
    agreeBackgroundCheck: true,
    agreeDotCompliance: true,
    ...over,
  };
}

describe("normalization", () => {
  it("formats 19810618 progressively to 1981-06-18", () => {
    expect(formatDateAsTyped("1981")).toBe("1981");
    expect(formatDateAsTyped("198106")).toBe("1981-06");
    expect(formatDateAsTyped("19810618")).toBe("1981-06-18");
    expect(formatDateAsTyped("1981-06-18")).toBe("1981-06-18");
  });

  it("rejects impossible dates", () => {
    expect(isCompleteIsoDate("2020-13-01")).toBe(false);
    expect(isCompleteIsoDate("2020-02-30")).toBe(false);
    expect(isCompleteIsoDate("1981-06-18")).toBe(true);
  });

  it("lowercases and validates email", () => {
    expect(normalizeEmail("  Jane.DOE@Example.COM ")).toBe("jane.doe@example.com");
    expect(isValidEmail("jane@example.com")).toBe(true);
    expect(isValidEmail("mkaamir.me.com")).toBe(false);
    expect(isValidEmail("not-an-email")).toBe(false);
    expect(isValidEmail("a@b")).toBe(false);
  });

  it("NANP phone: valid, +1, reject 00 prefix and short", () => {
    expect(parseNanpDigits("4165551212")).toBe("4165551212");
    expect(parseNanpDigits("+1 416 555-1212")).toBe("4165551212");
    expect(parseNanpDigits("14165551212")).toBe("4165551212");
    expect(isValidNanpPhone("0019214585")).toBe(false);
    expect(isValidNanpPhone("416555121")).toBe(false);
    expect(normalizePhoneStored("(416) 555-1212")).toBe("+14165551212");
  });

  it("Canadian postal A1A1A1 -> A1A 1A1", () => {
    expect(formatPostalCALive("n2r0n4")).toBe("N2R 0N4");
    expect(isValidPostalCA("N2R0N4")).toBe(true);
    expect(isValidPostalCA("A1A 1A1")).toBe(true);
    expect(isValidPostalCA("000000")).toBe(false);
    expect(isValidPostalCA("D1A 1A1")).toBe(false);
    expect(isValidPostalCA("N2R")).toBe(false);
  });

  it("US ZIP 5 or ZIP+4", () => {
    expect(isValidZipUS("75001")).toBe(true);
    expect(isValidZipUS("75001-1234")).toBe(true);
    expect(isValidZipUS("7500")).toBe(false);
    expect(isValidZipUS("ABCDE")).toBe(false);
    expect(liveNormalize("zip_code", "750011234")).toBe("75001-1234");
  });

  it("uppercases licence codes and preserves name case", () => {
    expect(liveNormalize("driver_license_number", "k358 756")).toBe("K358756");
    expect(liveNormalize("cdl_class", "ac")).toBe("AC");
    const f = normalizeForm(baseForm({ first_name: "  Mary  Jane  ", last_name: "O'Neil" }));
    expect(f.first_name).toBe("Mary Jane");
    expect(f.last_name).toBe("O'Neil");
  });

  it("blur-normalizes phone to display form", () => {
    expect(blurNormalize("phone", "4165551212")).toBe("(416) 555-1212");
    expect(blurNormalize("email", "  A@B.COM ")).toBe("a@b.com");
  });
});

describe("age and date relations", () => {
  it("DOB requires age >= 18", () => {
    expect(isAgeAtLeast18("2008-09-13", TODAY)).toBe(true);
    expect(isAgeAtLeast18("2008-09-14", TODAY)).toBe(false);
  });
});

describe("step 0 blocking", () => {
  it("blocks missing DL confirm and licence fields", () => {
    const e = validateStep0(snap({ dlFrontConfirmed: false, dlBackConfirmed: false, form: baseForm({ driver_license_number: "", cdl_class: "" }) }));
    expect(e.map((x) => x.field)).toEqual(expect.arrayContaining(["CDL_FRONT", "CDL_BACK", "driver_license_number", "cdl_class"]));
  });

  it("blocks issue date after expiry", () => {
    const e = validateStep0(snap({ form: baseForm({ license_issue_date: "2032-01-01", license_expiry: "2031-01-12" }) }));
    expect(e.some((x) => x.field === "license_issue_date")).toBe(true);
  });

  it("allows empty issue date", () => {
    const e = validateStep0(snap({ form: baseForm({ license_issue_date: "" }) }));
    expect(e.some((x) => x.field === "license_issue_date")).toBe(false);
  });
});

describe("step 1 blocking", () => {
  it("rejects invalid email and phone that are non-empty", () => {
    const e = validateStep1(
      snap({ form: baseForm({ email: "mkaamir.me.com", phone: "0019214585" }) }),
      TODAY,
    );
    expect(e.some((x) => x.field === "email")).toBe(true);
    expect(e.some((x) => x.field === "phone")).toBe(true);
  });

  it("requires province AND postal for CA, not OR", () => {
    const noRegion = validateStep1(snap({ form: baseForm({ address_region: "" }) }), TODAY);
    expect(noRegion.some((x) => x.field === "address_region")).toBe(true);
    const noPostal = validateStep1(snap({ form: baseForm({ address_postal: "" }) }), TODAY);
    expect(noPostal.some((x) => x.field === "address_postal")).toBe(true);
  });

  it("requires US state AND ZIP", () => {
    const e = validateStep1(
      snap({
        form: baseForm({
          address_country: "US",
          address_region: "",
          zip_code: "",
          address_postal: "",
        }),
      }),
      TODAY,
    );
    expect(e.some((x) => x.field === "address_region")).toBe(true);
    expect(e.some((x) => x.field === "zip_code")).toBe(true);
  });

  it("requires DOB age 18+", () => {
    const e = validateStep1(snap({ form: baseForm({ date_of_birth: "2015-01-01" }) }), TODAY);
    expect(e.some((x) => x.field === "date_of_birth")).toBe(true);
  });

  it("passes a complete valid CA personal-info set", () => {
    expect(validateStep1(snap(), TODAY)).toEqual([]);
  });
});

describe("step 2 references", () => {
  it("rejects non-empty invalid email even if phone is empty", () => {
    const e = validateStep2(
      snap({
        refs: [
          ref(),
          ref({ full_name: "Pat", phone: "", email: "not-an-email" }),
        ],
      }),
    );
    expect(e.some((x) => x.field === "refs.1.email")).toBe(true);
  });

  it("accepts valid email without phone", () => {
    const e = validateStep2(
      snap({
        refs: [ref(), ref({ full_name: "Pat Lee", phone: "", email: "pat@co.com" })],
      }),
    );
    expect(e.filter((x) => x.field.startsWith("refs.1"))).toEqual([]);
  });
});

describe("step 3 documents and submit revalidation", () => {
  it("blocks missing required documents", () => {
    const e = validateStep3(snap({ documents: {} }));
    expect(e.map((x) => x.field)).toEqual(
      expect.arrayContaining([
        "documents.dot_medical",
        "documents.mvr",
        "documents.drug_test",
        "documents.psp_report",
      ]),
    );
  });

  it("final submit re-runs earlier steps (stale invalid email blocks)", () => {
    const e = validateSubmit(
      snap({ form: baseForm({ email: "mkaamir.me.com" }) }),
      TODAY,
    );
    expect(e.some((x) => x.field === "email")).toBe(true);
  });

  it("complete snapshot submits", () => {
    expect(validateSubmit(snap(), TODAY)).toEqual([]);
  });

  it("optional documents do not block submit", () => {
    const e = validateSubmit(snap(), TODAY);
    expect(e.some((x) => x.field === "documents.ss_card")).toBe(false);
    expect(e.some((x) => x.field === "documents.void_cheque")).toBe(false);
  });

  it("step continue does not require documents; submit does", () => {
    const s = snap({ documents: {} });
    expect(validateOnboardingStep(1, s, TODAY)).toEqual([]);
    expect(validateSubmit(s, TODAY).some((x) => x.field.startsWith("documents."))).toBe(true);
  });
});

describe("jobs and phones", () => {
  it("rejects end date before start", () => {
    const e = validateStep2(snap({ jobs: [job({ start_date: "2020-06-01", end_date: "2019-01-01" })] }));
    expect(e.some((x) => x.field === "jobs.0.end_date")).toBe(true);
  });

  it("rejects malformed supervisor phone only when present", () => {
    const empty = validateStep2(snap({ jobs: [job({ supervisor_phone: "" })] }));
    expect(empty.some((x) => x.field === "jobs.0.supervisor_phone")).toBe(false);
    const bad = validateStep2(snap({ jobs: [job({ supervisor_phone: "0019214585" })] }));
    expect(bad.some((x) => x.field === "jobs.0.supervisor_phone")).toBe(true);
  });

  it("formats stored E.164 for display without rewriting in-progress typing", () => {
    expect(displayPhone("+14165551212")).toBe("(416) 555-1212");
    expect(displayPhone("416555121")).toBe("416555121");
  });
});

describe("non-driver contact", () => {
  it("rejects invalid email/phone with the same rules", () => {
    const e = validateNonDriverContact(baseForm({ email: "mkaamir.me.com", phone: "0019214585" }));
    expect(e.some((x) => x.field === "email")).toBe(true);
    expect(e.some((x) => x.field === "phone")).toBe(true);
  });

  it("does not require DOB or documents", () => {
    const e = validateNonDriverContact(baseForm({ date_of_birth: "", sex: "" }));
    expect(e.some((x) => x.field === "date_of_birth")).toBe(false);
    expect(e.some((x) => x.field.startsWith("documents."))).toBe(false);
  });
});
