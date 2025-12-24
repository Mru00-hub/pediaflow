import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { PatientInput, ClinicalDiagnosis, IVSetType } from '../types';
import { Activity, Thermometer, Droplets, HeartPulse } from 'lucide-react';

// 1. Zod Schema - Mirrors 'PatientRequest' in main.py strict validation
const schema = z.object({
  age_months: z.number().min(0).max(216),
  weight_kg: z.number().min(0.5).max(120),
  sex: z.enum(['M', 'F']),
  muac_cm: z.number().min(5).max(40),
  temp_celsius: z.number().min(25).max(45),
  systolic_bp: z.number().min(30).max(250),
  heart_rate: z.number().min(30).max(300),
  respiratory_rate_bpm: z.number().min(10).max(150),
  sp_o2_percent: z.number().min(0).max(100),
  capillary_refill_sec: z.number().min(0).max(20),
  hemoglobin_g_dl: z.number().min(1).max(25),
  diagnosis: z.nativeEnum(ClinicalDiagnosis),
  iv_set_available: z.nativeEnum(IVSetType).transform((val) => Number(val)), 
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
      iv_set_available: IVSetType.MICRO_DRIP, // 60 drops/ml
      sp_o2_percent: 98,
      capillary_refill_sec: 2
    }
  });

  return (
    <form onSubmit={handleSubmit((d) => onSubmit(d as any))} className="space-y-6 bg-white p-6 rounded-xl shadow-sm border border-slate-200">
      
      {/* SECTION 1: DEMOGRAPHICS */}
      <div className="space-y-4">
        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider border-b pb-2">Patient Demographics</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700">Age (Months)</label>
            <input {...register("age_months", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 p-2 border" />
            {errors.age_months && <p className="text-red-500 text-xs">{errors.age_months.message}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Weight (kg)</label>
            <input step="0.1" {...register("weight_kg", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 p-2 border" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">MUAC (cm)</label>
            <input step="0.1" {...register("muac_cm", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 p-2 border" />
            <p className="text-xs text-slate-400">{'<'}11.5cm indicates SAM</p>
          </div>
           <div>
            <label className="block text-sm font-medium text-slate-700">Sex</label>
            <select {...register("sex")} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border">
              <option value="M">Male</option>
              <option value="F">Female</option>
            </select>
          </div>
        </div>
      </div>

      {/* SECTION 2: VITALS (Visual Grouping) */}
      <div className="space-y-4">
        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider border-b pb-2 flex items-center gap-2">
          <Activity className="w-4 h-4" /> Vitals & Triage
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div className="relative">
            <label className="block text-sm font-medium text-slate-700">Heart Rate</label>
            <input type="number" {...register("heart_rate", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
            <HeartPulse className="absolute right-2 top-8 w-4 h-4 text-slate-400" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Systolic BP</label>
            <input type="number" {...register("systolic_bp", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
          </div>
           <div>
            <label className="block text-sm font-medium text-slate-700">Temp (°C)</label>
            <input step="0.1" {...register("temp_celsius", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
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
            <label className="block text-sm font-medium text-slate-700">Hb (g/dL)</label>
            <input step="0.1" {...register("hemoglobin_g_dl", { valueAsNumber: true })} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm p-2 border" />
          </div>
        </div>
      </div>

      {/* SECTION 3: CONTEXT */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">Working Diagnosis</label>
        <select {...register("diagnosis")} className="w-full p-2 border rounded bg-slate-50">
          <option value={ClinicalDiagnosis.UNKNOWN}>Undifferentiated Shock</option>
          <option value={ClinicalDiagnosis.SEVERE_DEHYDRATION}>Severe Dehydration (Diarrhea)</option>
          <option value={ClinicalDiagnosis.SEPTIC_SHOCK}>Septic Shock</option>
          <option value={ClinicalDiagnosis.DENGUE_SHOCK}>Dengue Shock Syndrome</option>
          <option value={ClinicalDiagnosis.SAM_DEHYDRATION}>SAM + Dehydration</option>
        </select>
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
