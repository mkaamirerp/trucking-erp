import type {
  Broker,
  BrokerContact,
  CustomsBroker,
  Driver,
  LoadDocumentParseReference,
  LoadNote,
  Trailer,
  Truck,
} from "@/api";
import type { OperatorLoadStatusInput } from "@/loads/operatorLoadStatus";
import type { DraftStop, IntakeProposedFields, LoadWorkspaceMode, WorkspaceSection } from "./loadWorkspaceShared";

export type LoadWorkspaceFormProps = {
  mode: LoadWorkspaceMode;
  intakeProposed: IntakeProposedFields | null;
  saving: boolean;
  freightBrokers: Broker[];
  brokerContacts: BrokerContact[];
  drivers: Driver[];
  trucks: Truck[];
  trailers: Trailer[];
  customsBrokers: CustomsBroker[];
  customsMessage: string | null;
  customsBrokerLocked: boolean;
  onCustomsBrokerChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  onConfirmSnapshot?: () => void;
  showOperationalNotesTimeline: boolean;
  loadNotes: LoadNote[];
  newNoteBody: string;
  setNewNoteBody: (v: string) => void;
  onAddNote: () => void;
  focusDoc: (opts: { tokens: string[]; fallbackToken?: string }) => void;
  verificationTabIndex: Map<string, number>;
  status: string;
  loadNumber: string;
  setLoadNumber: (v: string) => void;
  brokerId: number | null;
  setBrokerId: (v: number | null) => void;
  brokerContactId: number | null;
  setBrokerContactId: (v: number | null) => void;
  brokerNameSnapshot: string;
  setBrokerNameSnapshot: (v: string) => void;
  brokerContactNameSnapshot: string;
  setBrokerContactNameSnapshot: (v: string) => void;
  brokerContactPhoneSnapshot: string;
  setBrokerContactPhoneSnapshot: (v: string) => void;
  brokerContactExtensionSnapshot: string;
  setBrokerContactExtensionSnapshot: (v: string) => void;
  brokerContactEmailSnapshot: string;
  setBrokerContactEmailSnapshot: (v: string) => void;
  brokerLoadReference: string;
  setBrokerLoadReference: (v: string) => void;
  loadReferences: LoadDocumentParseReference[];
  freightMode: string;
  setFreightMode: (v: string) => void;
  equipmentType: string;
  setEquipmentType: (v: string) => void;
  trailerType: string;
  setTrailerType: (v: string) => void;
  trailerSize: string;
  setTrailerSize: (v: string) => void;
  commodity: string;
  setCommodity: (v: string) => void;
  estimatedWeight: string;
  setEstimatedWeight: (v: string) => void;
  hazmat: "unset" | "yes" | "no";
  setHazmat: (v: "unset" | "yes" | "no") => void;
  temperatureRequirement: string;
  setTemperatureRequirement: (v: string) => void;
  palletCaseCount: string;
  setPalletCaseCount: (v: string) => void;
  rate: string;
  setRate: (v: string) => void;
  customerRate: string;
  setCustomerRate: (v: string) => void;
  miles: string;
  setMiles: (v: string) => void;
  driverId: number | null;
  truckId: number | null;
  trailerAssetId: number | null;
  activeTripId?: number | null;
  operatorStatusInput: OperatorLoadStatusInput;
  customsBrokerId: number | null;
  internalNotes: string;
  setInternalNotes: (v: string) => void;
  draftStops: DraftStop[];
  sortedDraftStops: DraftStop[];
  updateStop: (key: string, patch: Partial<DraftStop>) => void;
  removeStop: (key: string) => void;
  addStop: () => void;
  moveStop: (key: string, dir: -1 | 1) => void;
  visibleSections?: WorkspaceSection[];
  editableSections?: WorkspaceSection[];
  readOnly?: boolean;
  renderNotes?: boolean;
  workspaceHasRateConfirmationPdf?: boolean;
};
