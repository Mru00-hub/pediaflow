import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { ClinicalDiagnosis, IVSetType, OngoingLosses } from '../types';
import type { PatientInput } from '../types';
import { Activity, Droplets, HeartPulse, ClipboardList, FlaskConical } from 'lucide-react';

// 1. Zod Schema - Matches Backend Model 100%
const schema = z.object({
  // Demographics
  age_months: z.number().min(0).max(216),
  weight_kg: z.number().min(0.5).max(120),
  sex: z.enum(['M', 'F']),
  muac_cm: z.number().min(5).max(40),
  height_cm: z.number().min(20).max(250).optional().or(z.nan()),

  // Vitals
  temp_celsius: z.number().min(25).max(45),
  systolic_bp: z.number().min(30).max(250),
  diastolic_bp: z.number().min(10).max(200).optional().or(z.nan()),
  heart_rate: z.number().min(30).max(300),
  respiratory_rate_bpm: z.number().min(10).max(150),
  sp_o2_percent: z.number().min(0).max(100),
  capillary_refill_sec: z.number().min(0).max(20),

  // Labs
  hemoglobin_g_dl: z.number().min(1).max(25),
  current_sodium: z.number().min(100).max(180).optional().or(z.nan()),
  current_glucose: z.number().min(10).max(1000).optional().or(z.nan()),
  hematocrit_pct: z.number().min(5).max(80).optional().or(z.nan()), // Current Hct
  baseline_hematocrit_pct: z.number().min(5).max(80).optional().or(z.nan()), // [NEW] Baseline Hct
  lactate_mmol_l: z.number().min(0).max(30).optional().or(z.nan()),
  plasma_albumin_g_dl: z.number().min(1).max(6).optional().or(z.nan()),
  platelet_count: z.number().min(1000).max(1000000).optional().or(z.nan()),

  // Context & Logic
  diagnosis: z.nativeEnum(ClinicalDiagnosis),
  ongoing_losses_severity: z.nativeEnum(OngoingLosses).transform((val) => Number(val)),
  iv_set_available: z.nativeEnum(IVSetType).transform((val) => Number(val)),
  illness_day: z.number().min(1).max(30).optional().or(z.nan()),
  time_since_last_urine_hours: z.number().min(0).max(72).optional().or(z.nan()),
  target_hemoglobin_g_dl: z.number().min(4).max(20).optional().or(z.nan()), // [NEW] Target Hb
  baseline_hepatomegaly: z.boolean().optional(),
});

interface Props {
  onSubmit: (data: PatientInput) => void;
  loading: boolean;
}

export const InputForm: React.FC<Props> = ({ onSubmit, loading }) => {
  const { register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodResolver(schema),
    defaultValues: {
      sex: 'M',
      diagnosis: ClinicalDiagnosis.UNKNOWN,
      iv_set_available: IVSetType.MICRO_DRIP, 
      ongoing_losses_severity: OngoingLosses.NONE,
      sp_o2_percent: 98,
      capillary_refill_sec: 2,
      baseline_hepatomegaly: false,
      target_hemoglobin_g_dl: 10 // Default from backend
    }
  });

  // Safety: Removes empty number fields to prevent crashes
  const processSubmit = (data: any) => {
    const cleanData = Object.fromEntries(
      Object.entries(data).filter(([_, v]) => v !== undefined && v !== null && !Number.isNaN(v))
    );
    onSubmit(cleanData as PatientInput);
  };

  return (
    <form onSubmit={handleSubmit(processSubmit)} className="space-y-6 bg-white p-6 rounded-xl shadow-sm border border-slate-200">
      
      {/* SECTION 1: DEMOGRAPHICS */}
      <div className="space-y-4">
        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider border-b pb-2 flex items-center gap-2">
           User Profile
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700">Age (Months)</label>
            <input type="number" {...register("age_months", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
            {errors.age_months && <p className="text-red-500 text-xs">{errors.age_months.message}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Weight (kg)</label>
            <input type="number" step="0.1" {...register("weight_kg", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Sex</label>
            <select {...register("sex")} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border bg-white">
              <option value="M">Male</option>
              <option value="F">Female</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Height (cm)</label>
            <input type="number" step="1" {...register("height_cm", { valueAsNumber: true })} placeholder="Optional" className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
          </div>
          <div className="col-span-2 md:col-span-1">
            <label className="block text-sm font-medium text-slate-700">MUAC (cm)</label>
            <div className="flex gap-2 items-center">
                <input type="number" step="0.1" {...register("muac_cm", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
                <span className="text-xs text-slate-400 whitespace-nowrap">{'<'}11.5 = SAM</span>
            </div>
          </div>
        </div>
      </div>

      {/* SECTION 2: VITALS */}
      <div className="space-y-4">
        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider border-b pb-2 flex items-center gap-2">
          <Activity className="w-4 h-4" /> Vitals
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="relative">
            <label className="block text-sm font-medium text-slate-700">Heart Rate</label>
            <input type="number" {...register("heart_rate", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
            <HeartPulse className="absolute right-2 top-8 w-4 h-4 text-slate-400 opacity-50" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Systolic BP</label>
            <input type="number" {...register("systolic_bp", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Diastolic BP</label>
            <input type="number" {...register("diastolic_bp", { valueAsNumber: true })} placeholder="Optional" className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
          </div>
           <div>
            <label className="block text-sm font-medium text-slate-700">Temp (°C)</label>
            <input type="number" step="0.1" {...register("temp_celsius", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Resp Rate</label>
            <input type="number" {...register("respiratory_rate_bpm", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">SpO2 (%)</label>
            <input type="number" {...register("sp_o2_percent", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Cap Refill (sec)</label>
            <input type="number" {...register("capillary_refill_sec", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
          </div>
           <div>
            <label className="block text-sm font-medium text-slate-700">Hb (g/dL)</label>
            <input type="number" step="0.1" {...register("hemoglobin_g_dl", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
          </div>
        </div>
      </div>

      {/* SECTION 3: LABS (Optional but Critical) */}
      <div className="space-y-4">
        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider border-b pb-2 flex items-center gap-2">
          <FlaskConical className="w-4 h-4" /> Labs (Optional)
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 bg-slate-50 p-4 rounded-lg border border-slate-100">
             <div>
                <label className="block text-xs font-medium text-slate-500">Glucose (mg/dL)</label>
                <input type="number" {...register("current_glucose", { valueAsNumber: true })} placeholder="90" className="mt-1 w-full p-2 border rounded text-sm" />
             </div>
             <div>
                <label className="block text-xs font-medium text-slate-500">Lactate (mmol/L)</label>
                <input type="number" step="0.1" {...register("lactate_mmol_l", { valueAsNumber: true })} placeholder="--" className="mt-1 w-full p-2 border rounded text-sm" />
             </div>
             <div>
                <label className="block text-xs font-medium text-slate-500">Current Hct (%)</label>
                <input type="number" step="0.1" {...register("hematocrit_pct", { valueAsNumber: true })} placeholder="35" className="mt-1 w-full p-2 border rounded text-sm" />
             </div>
             <div>
                <label className="block text-xs font-medium text-slate-500">Baseline Hct (%)</label>
                <input type="number" step="0.1" {...register("baseline_hematocrit_pct", { valueAsNumber: true })} placeholder="For Dengue" className="mt-1 w-full p-2 border rounded text-sm" />
             </div>
             <div>
                <label className="block text-xs font-medium text-slate-500">Sodium (mEq/L)</label>
                <input type="number" {...register("current_sodium", { valueAsNumber: true })} placeholder="140" className="mt-1 w-full p-2 border rounded text-sm" />
             </div>
             <div>
                <label className="block text-xs font-medium text-slate-500">Albumin (g/dL)</label>
                <input type="number" step="0.1" {...register("plasma_albumin_g_dl", { valueAsNumber: true })} placeholder="--" className="mt-1 w-full p-2 border rounded text-sm" />
             </div>
             <div>
                <label className="block text-xs font-medium text-slate-500">Platelets (/µL)</label>
                <input type="number" {...register("platelet_count", { valueAsNumber: true })} placeholder="--" className="mt-1 w-full p-2 border rounded text-sm" />
             </div>
             <div>
                <label className="block text-xs font-medium text-slate-500">Target Hb (g/dL)</label>
                <input type="number" step="0.1" {...register("target_hemoglobin_g_dl", { valueAsNumber: true })} placeholder="10.0" className="mt-1 w-full p-2 border rounded text-sm" />
             </div>
        </div>
      </div>

      {/* SECTION 4: CLINICAL CONTEXT */}
      <div className="space-y-4">
        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider border-b pb-2 flex items-center gap-2">
          <ClipboardList className="w-4 h-4" /> Clinical Context
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Diagnosis */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Working Diagnosis</label>
              <select {...register("diagnosis")} className="w-full p-2 border rounded bg-white">
                <option value={ClinicalDiagnosis.UNKNOWN}>Undifferentiated Shock</option>
                <option value={ClinicalDiagnosis.SEVERE_DEHYDRATION}>Severe Dehydration (Diarrhea)</option>
                <option value={ClinicalDiagnosis.SEPTIC_SHOCK}>Septic Shock</option>
                <option value={ClinicalDiagnosis.DENGUE_SHOCK}>Dengue Shock Syndrome</option>
                <option value={ClinicalDiagnosis.SAM_DEHYDRATION}>SAM + Dehydration</option>
              </select>
            </div>

            {/* Ongoing Losses */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Ongoing Losses (Diarrhea/Vomit)</label>
              <select {...register("ongoing_losses_severity", { valueAsNumber: true })} className="w-full p-2 border rounded bg-white">
                <option value={OngoingLosses.NONE}>None</option>
                <option value={OngoingLosses.MILD}>Mild (5 ml/kg/hr)</option>
                <option value={OngoingLosses.MODERATE}>Moderate (7 ml/kg/hr)</option>
                <option value={OngoingLosses.SEVERE}>Severe (10 ml/kg/hr)</option>
              </select>
            </div>

            {/* Renal Status */}
            <div>
                <label className="block text-sm font-medium text-slate-700">Time since last urine (Hours)</label>
                <input type="number" step="0.5" {...register("time_since_last_urine_hours", { valueAsNumber: true })} placeholder="0" className="mt-1 w-full p-2 border rounded" />
            </div>

             {/* Illness Day */}
            <div>
              <label className="block text-sm font-medium text-slate-700">Illness Day (If Dengue)</label>
              <input type="number" {...register("illness_day", { valueAsNumber: true })} placeholder="e.g. 4" className="mt-1 w-full p-2 border rounded" />
            </div>
            
            {/* IV Set */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">IV Set Available</label>
              <select {...register("iv_set_available", { valueAsNumber: true })} className="w-full p-2 border rounded bg-white">
                <option value={IVSetType.MICRO_DRIP}>Micro Drip (60 drops/ml)</option>
                <option value={IVSetType.MACRO_DRIP}>Macro Drip (20 drops/ml)</option>
              </select>
            </div>

             {/* Hepatomegaly */}
            <div className="flex items-center gap-3 mt-6 border p-3 rounded-lg bg-slate-50">
                <input type="checkbox" {...register("baseline_hepatomegaly")} className="w-5 h-5 text-blue-600 rounded" />
                <label className="text-sm font-medium text-slate-700">Hepatomegaly (Liver &gt; 2cm)</label>
            </div>
        </div>
      </div>

      <button 
        type="submit" 
        disabled={loading}
        className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded transition-colors flex justify-center items-center gap-2"
      >
        {loading ? <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div> : <><Droplets className="w-5 h-5" /> Generate Fluid Protocol</>}
      </button>
    </form>
  );
};
