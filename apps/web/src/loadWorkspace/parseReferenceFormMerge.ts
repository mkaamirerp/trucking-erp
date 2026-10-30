import type { LoadReparseChange } from "@/api";
import type { LoadPersistParams } from "@/loadWorkspace/loadWorkspaceShared";

function readFormScalar(params: LoadPersistParams, field: string): unknown {
  switch (field) {
    case "rate":
      return params.rate;
    case "broker_load_reference":
      return params.brokerLoadReference;
    case "broker_name_snapshot":
      return params.brokerNameSnapshot;
    case "broker_contact_name_snapshot":
      return params.brokerContactNameSnapshot;
    case "broker_contact_phone_snapshot":
      return params.brokerContactPhoneSnapshot;
    case "broker_contact_extension_snapshot":
      return params.brokerContactExtensionSnapshot;
    case "broker_contact_email_snapshot":
      return params.brokerContactEmailSnapshot;
    case "mode":
      return params.mode;
    case "equipment_type":
      return params.equipmentType;
    case "trailer_type":
      return params.trailerType;
    case "trailer_size":
      return params.trailerSize;
    case "commodity":
      return params.commodity;
    case "estimated_weight":
      return params.estimatedWeight;
    case "miles":
      return params.miles;
    case "temperature_requirement":
      return params.temperatureRequirement;
    case "pallet_case_count":
      return params.palletCaseCount;
    case "hazmat_flag":
      return params.hazmat;
    default:
      return undefined;
  }
}

/** Replace row current_value with live form values for the Parse PDF review table. */
export function mergeParseReferenceRowsWithForm(
  rows: LoadReparseChange[],
  params: LoadPersistParams,
): LoadReparseChange[] {
  return rows.map((row) => {
    const stop = row.field.match(/^stops\[(\d+)\]\.([a-z0-9_]+)$/);
    if (stop) {
      const index = Number(stop[1]);
      const key = stop[2];
      const stopRow = params.draftStops[index];
      if (!stopRow) return row;
      const current = (stopRow as Record<string, unknown>)[key] ?? null;
      return { ...row, current_value: current };
    }
    const reference = row.field.match(/^references\[(\d+)\]\.(kind|value)$/);
    if (reference) {
      const index = Number(reference[1]);
      const key = reference[2] as "kind" | "value";
      const ref = params.loadReferences[index];
      if (!ref) return row;
      return { ...row, current_value: ref[key] };
    }
    const scalar = readFormScalar(params, row.field.replace(/^extracted\./, ""));
    if (scalar !== undefined) {
      return { ...row, current_value: scalar };
    }
    return row;
  });
}
