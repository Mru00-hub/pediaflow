// types.ts

// --- ENUMS (Matching models.py) ---

export enum FluidType {
  RL = "ringer_lactate",
  NS = "normal_saline_0.9",
  D5_NS = "dextrose_5_normal_saline",
  RESOMAL = "resomal_rehydration_sol",
  PRBC = "packed_red_blood_cells",
  COLLOID_ALBUMIN = "albumin_5_percent",
  ORS_SOLUTION = "oral_rehydration_solution",
  HALF_NS = "half_normal_saline"
}

export enum ClinicalDiagnosis {
  SEVERE_DEHYDRATION = "severe_dehydration",
  SEPTIC_SHOCK = "septic_shock",
  DENGUE_SHOCK = "dengue_shock_syndrome",
  SAM_DEHYDRATION = "sam_severe_malnutrition",
  UNKNOWN = "undifferentiated_shock",
  SEVERE_ANEMIA = "severe_anemia"
}

export enum IVSetType {
  MICRO_DRIP = 60,
  MACRO_DRIP = 20
}

export enum OngoingLosses {
  NONE = 0,
  MILD = 5,
  MODERATE = 7,
  SEVERE = 10
}

// --- DATA STRUCTURES ---

[span_0](start_span)// Matches class PatientInput in models.py[span_0](end_span)
export interface PatientInput {
  // Demographics
  age_months: number;
  weight_kg: number;
  sex: 'M' | 'F';
  muac_cm: number;
  height_cm?: number; // Optional

  // Vitals
  temp_celsius: number;
  systolic_bp: number;
  diastolic_bp?: number;
  heart_rate: number;
  respiratory_rate_bpm: number;
  sp_o2_percent: number;
  capillary_refill_sec: number;

  // Labs
  hemoglobin_g_dl: number;
  current_sodium?: number; // Defaults to 140 in backend
  current_glucose?: number; // Defaults to 90
  hematocrit_pct?: number; // Defaults to 35
  lactate_mmol_l?: number;
  plasma_albumin_g_dl?: number;
  platelet_count?: number;

  // Clinical Context
  diagnosis: ClinicalDiagnosis;
  ongoing_losses_severity?: OngoingLosses;
  iv_set_available?: IVSetType;
  illness_day?: number; [span_1](start_span)// Required for Dengue[span_1](end_span)
  baseline_hepatomegaly?: boolean;
  time_since_last_urine_hours?: number;
}

[span_2](start_span)// Matches class SafetyAlerts in models.py[span_2](end_span)
export interface SafetyAlerts {
  risk_pulmonary_edema: boolean;
  risk_volume_overload: boolean;
  risk_cerebral_edema: boolean;
  risk_hypoglycemia: boolean;
  hydrocortisone_needed: boolean;
  risk_ketoacidosis: boolean;
  sam_heart_warning: boolean;
  anemia_dilution_warning: boolean;
  dengue_leak_warning: boolean;
}

[span_3](start_span)// Matches PrescriptionResponse in main.py[span_3](end_span)
export interface PrescriptionResponse {
  recommended_fluid: FluidType;
  bolus_volume_ml: number;
  infusion_duration_min: number;
  
  // Hardware Instructions
  flow_rate_ml_hr: number;
  drops_per_minute: number;
  seconds_per_drop: number;
  iv_set_used: string;

  // Safety & Predictions
  max_safe_infusion_rate_ml_hr: number;
  max_allowed_bolus_volume_ml: number;
  predicted_bp_rise: number;
  stop_trigger_heart_rate: number;
  stop_trigger_respiratory_rate: number;
  
  alerts: SafetyAlerts;
  
  // UX
  human_readable_summary: string;
  trajectory: Array<{
    time: number;
    map: number;
    lung_water: number;
    leak_rate: number;
    hct: number;
  }>;
  
  generated_at: string;
}

[span_4](start_span)// Matches SimulationRequest in main.py[span_4](end_span)
export interface SimulationRequest {
  patient: PatientInput;
  fluid_type: string;
  volume_ml: number;
  duration_min: number;
}

export interface SimulationResponse {
  summary: {
    bp_start: number;
    bp_end: number;
    safety_alerts: string[];
  };
  graph_data: Array<any>;
}
