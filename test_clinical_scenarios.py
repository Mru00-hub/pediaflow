import unittest
import math
from core_physics import PediaFlowPhysicsEngine
from models import (
    PatientInput, 
    ClinicalDiagnosis, 
    SimulationState, 
    PhysiologicalParams, 
    OngoingLosses
)
from constants import FluidType

class TestClinicalScenarios(unittest.TestCase):
    """
    Simulates 8 Critical Real-World Patient Cases to verify Physics & Logic.
    Run with: python -m unittest tests/test_clinical_scenarios.py
    """

    def create_base_patient(self, diagnosis, weight=10.0, muac=14.0):
        # Helper to create a standard 2-year-old
        return {
            'age_months': 24,
            'weight_kg': weight,
            'sex': 'M',
            'muac_cm': muac,
            'temp_celsius': 37.0,
            'hemoglobin_g_dl': 10.0,
            'systolic_bp': 80, 
            'heart_rate': 140,
            'capillary_refill_sec': 3,
            'sp_o2_percent': 98,
            'respiratory_rate_bpm': 35,
            'current_sodium': 135,
            'current_glucose': 80,
            'hematocrit_pct': 35.0,
            'diagnosis': diagnosis,
            'illness_day': 3,
            'ongoing_losses_severity': OngoingLosses.NONE
        }

    # --- EXISTING TESTS (Refined) ---

    def test_01_dengue_leak_vs_normal(self):
        """[PHYSICS] Does Dengue (Day 5) leak 3x more than normal?"""
        print("\nTEST 1: Dengue Capillary Leak")
        
        # A: Standard Dehydration
        data_a = self.create_base_patient(ClinicalDiagnosis.SEVERE_DEHYDRATION)
        twin_a = PediaFlowPhysicsEngine.create_digital_twin(data_a)
        
        # B: Dengue Day 5 (Critical Phase)
        data_b = self.create_base_patient(ClinicalDiagnosis.DENGUE_SHOCK)
        data_b['illness_day'] = 5 
        twin_b = PediaFlowPhysicsEngine.create_digital_twin(data_b)
        
        # Give 20ml/kg
        res_a = PediaFlowPhysicsEngine.run_simulation(
            twin_a.initial_state, twin_a.physics_params, FluidType.RL, 200, 60
        )
        res_b = PediaFlowPhysicsEngine.run_simulation(
            twin_b.initial_state, twin_b.physics_params, FluidType.RL, 200, 60
        )
        
        leak_a = res_a['fluid_leaked_percentage']
        leak_b = res_b['fluid_leaked_percentage']
        print(f"  > Normal Leak: {leak_a}% | Dengue Leak: {leak_b}%")
        
        self.assertTrue(leak_b > leak_a * 2.0, "Dengue did not leak enough vs control")

    def test_02_sam_heart_fragility(self):
        """[MECHANICS] Does SAM heart fail (Edema) faster than Normal heart?"""
        print("\nTEST 2: SAM Heart Fragility")
        
        # A: Normal Child (Well Hydrated)
        data_a = self.create_base_patient(ClinicalDiagnosis.UNKNOWN, muac=15)
        twin_a = PediaFlowPhysicsEngine.create_digital_twin(data_a)
        
        # B: SAM Child (Well Hydrated) - Same weight, weak heart
        data_b = self.create_base_patient(ClinicalDiagnosis.UNKNOWN, muac=10.5)
        twin_b = PediaFlowPhysicsEngine.create_digital_twin(data_b)
        
        # Rapid Bolus Challenge (20ml/kg in 20 min)
        res_a = PediaFlowPhysicsEngine.run_simulation(
            twin_a.initial_state, twin_a.physics_params, FluidType.RL, 200, 20
        )
        res_b = PediaFlowPhysicsEngine.run_simulation(
            twin_b.initial_state, twin_b.physics_params, FluidType.RL, 200, 20
        )
        
        # Check Lung Water (Interstitial Pressure)
        p_lung_a = res_a['final_state'].p_interstitial_mmHg
        p_lung_b = res_b['final_state'].p_interstitial_mmHg
        print(f"  > Normal Lung P: {p_lung_a:.2f} | SAM Lung P: {p_lung_b:.2f}")

        self.assertTrue(p_lung_b > p_lung_a, "SAM heart handled load too well (should fail)")

    def test_03_renal_shutdown_aki(self):
        """[RENAL] Does Anuria (AKI) prevent urine output?"""
        print("\nTEST 3: Renal Shutdown (AKI)")
        data = self.create_base_patient(ClinicalDiagnosis.SEPTIC_SHOCK)
        data['time_since_last_urine_hours'] = 12.0 # Shutdown
        
        twin = PediaFlowPhysicsEngine.create_digital_twin(data)
        res = PediaFlowPhysicsEngine.run_simulation(
            twin.initial_state, twin.physics_params, FluidType.NS, 200, 60
        )
        
        urine = res['final_state'].q_urine_ml_min
        print(f"  > Urine Output: {urine:.4f} ml/min")
        self.assertLess(urine, 0.05, "Kidney made urine despite AKI")

    def test_04_ongoing_losses(self):
        """[FLUX] Does Cholera-like diarrhea deplete volume despite maintenance?"""
        print("\nTEST 4: Massive Diarrhea vs Maintenance")
        data = self.create_base_patient(ClinicalDiagnosis.SEVERE_DEHYDRATION)
        data['ongoing_losses_severity'] = OngoingLosses.SEVERE # 10ml/kg/hr
        
        twin = PediaFlowPhysicsEngine.create_digital_twin(data)
        # Give Maintenance (4ml/kg/hr) -> 40ml/hr
        res = PediaFlowPhysicsEngine.run_simulation(
            twin.initial_state, twin.physics_params, FluidType.RL, 40, 60
        )
        
        vol_start = twin.initial_state.v_blood_current_l
        vol_end = res['final_state'].v_blood_current_l
        print(f"  > Start Vol: {vol_start:.3f}L | End Vol: {vol_end:.3f}L")
        
        self.assertLess(vol_end, vol_start, "Maintenance failed to lose ground against Cholera")

    # --- NEW ROBUST TESTS ---

    def test_05_hemodilution_trap(self):
        """[HEMATOLOGY] Does aggressive fluid drop Hct dangerously?"""
        print("\nTEST 5: Hemodilution Trap")
        # Child with borderline anemia (Hb 6.0 -> Hct 18)
        data = self.create_base_patient(ClinicalDiagnosis.SEPTIC_SHOCK)
        data['hemoglobin_g_dl'] = 6.0
        data['hematocrit_pct'] = 18.0
        
        twin = PediaFlowPhysicsEngine.create_digital_twin(data)
        
        # Give 40ml/kg (Massive Volume)
        res = PediaFlowPhysicsEngine.run_simulation(
            twin.initial_state, twin.physics_params, FluidType.NS, 400, 60
        )
        
        hct_end = res['final_state'].current_hematocrit_dynamic
        print(f"  > Start Hct: 18.0% | End Hct: {hct_end:.1f}%")
        
        # Should detect the dilution alert
        triggers = res['triggers']
        self.assertTrue(any("Hemodilution" in t for t in triggers) or hct_end < 15.0, 
                        "Failed to flag critical hemodilution")

    def test_06_dka_glucose_response(self):
        """[METABOLIC] Does Saline drop glucose via dilution, but D5 spike it?"""
        print("\nTEST 6: DKA Glucose Dynamics")
        data = self.create_base_patient(ClinicalDiagnosis.SEVERE_DEHYDRATION)
        data['current_glucose'] = 400.0 # DKA Range
        
        twin = PediaFlowPhysicsEngine.create_digital_twin(data)
        
        # A: Give Saline (Should dilute glucose slightly)
        res_ns = PediaFlowPhysicsEngine.run_simulation(
            twin.initial_state, twin.physics_params, FluidType.NS, 200, 60
        )
        
        # B: Give D5 (Should spike glucose massively)
        res_d5 = PediaFlowPhysicsEngine.run_simulation(
            twin.initial_state, twin.physics_params, FluidType.D5_NS, 200, 60
        )
        
        gluc_ns = res_ns['final_state'].current_glucose_mg_dl
        gluc_d5 = res_d5['final_state'].current_glucose_mg_dl
        
        print(f"  > NS Glucose: {gluc_ns:.0f} | D5 Glucose: {gluc_d5:.0f}")
        
        self.assertLess(gluc_ns, 400, "Saline failed to dilute glucose")
        self.assertGreater(gluc_d5, 450, "D5 failed to spike glucose")

    def test_07_cerebral_salt_wasting(self):
        """[NEURO] Does giving Hypotonic fluid to Hyponatremic child cause brain swell?"""
        print("\nTEST 7: Cerebral Edema (Hyponatremia)")
        # Child with Hyponatremia (Na 125)
        data = self.create_base_patient(ClinicalDiagnosis.SEPTIC_SHOCK)
        data['current_sodium'] = 125.0
        
        twin = PediaFlowPhysicsEngine.create_digital_twin(data)
        
        # Give 1/2 NS (Hypotonic) - Dangerous!
        # This pushes free water into cells (Osmotic Shift)
        res = PediaFlowPhysicsEngine.run_simulation(
            twin.initial_state, twin.physics_params, FluidType.HALF_NS, 200, 60
        )
        
        # Check Intracellular Volume (Brain Swelling Proxy)
        v_icf_start = twin.initial_state.v_intracellular_current_l
        v_icf_end = res['final_state'].v_intracellular_current_l
        
        delta_ml = (v_icf_end - v_icf_start) * 1000
        print(f"  > Cell Volume Change: +{delta_ml:.1f} ml")
        
        # Cells MUST swell with hypotonic fluid in hyponatremia
        self.assertGreater(delta_ml, 5.0, "Cells did not swell despite hypotonic challenge")

    def test_08_frank_starling_plateau(self):
        """[CARDIAC] Does Cardiac Output plateau after optimal preload?"""
        print("\nTEST 8: Frank-Starling Law")
        data = self.create_base_patient(ClinicalDiagnosis.SEPTIC_SHOCK)
        twin = PediaFlowPhysicsEngine.create_digital_twin(data)
        
        # Step 1: Give 100ml (Should boost BP significantly)
        res_1 = PediaFlowPhysicsEngine.run_simulation(
            twin.initial_state, twin.physics_params, FluidType.NS, 100, 15
        )
        bp_rise_1 = res_1['predicted_map_rise']
        
        # Step 2: Give ANOTHER 100ml on top of the first (Should have diminishing returns)
        res_2 = PediaFlowPhysicsEngine.run_simulation(
            res_1['final_state'], twin.physics_params, FluidType.NS, 100, 15
        )
        bp_rise_2 = res_2['predicted_map_rise']
        
        print(f"  > 1st Bolus Rise: +{bp_rise_1} mmHg")
        print(f"  > 2nd Bolus Rise: +{bp_rise_2} mmHg")
        
        self.assertLess(bp_rise_2, bp_rise_1, "Heart did not show diminishing returns (Starling Plateau)")

if __name__ == '__main__':
    unittest.main()
