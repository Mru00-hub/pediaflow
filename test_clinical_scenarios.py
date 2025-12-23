import unittest
from app import (
    PediaFlowPhysicsEngine, PatientInput, ClinicalDiagnosis, 
    FluidType, SimulationState, PhysiologicalParams, OngoingLosses
)

class TestClinicalScenarios(unittest.TestCase):
    """
    Simulates real-world patient cases to verify clinical logic.
    """

    def create_base_patient(self, diagnosis, weight=10.0, muac=14.0):
        return {
            'age_months': 24,
            'weight_kg': weight,
            'sex': 'M',
            'muac_cm': muac,
            'temp_celsius': 37.0,
            'hemoglobin_g_dl': 10.0,
            'systolic_bp': 80, # Shock state
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

    def test_01_dengue_leak_vs_normal(self):
        """
        SCENARIO: Does a Dengue patient leak more fluid than a standard dehydration patient?
        We compare two identical twins: one with Diarrhea, one with Dengue (Day 5).
        """
        print("\nCLINICAL TEST 1: Dengue Capillary Leak")
        
        # Patient A: Simple Dehydration (Intact vessels)
        data_a = self.create_base_patient(ClinicalDiagnosis.SEVERE_DEHYDRATION)
        twin_a = PediaFlowPhysicsEngine.create_digital_twin(data_a)
        
        # Patient B: Dengue Shock Day 5 (Leaky vessels, Sigma=0.3)
        data_b = self.create_base_patient(ClinicalDiagnosis.DENGUE_SHOCK)
        data_b['illness_day'] = 5 
        twin_b = PediaFlowPhysicsEngine.create_digital_twin(data_b)
        
        # Give both 20ml/kg RL over 60 mins
        vol = 200; duration = 60
        
        res_a = PediaFlowPhysicsEngine.run_simulation(
            twin_a.initial_state, twin_a.physics_params, FluidType.RL, vol, duration
        )
        res_b = PediaFlowPhysicsEngine.run_simulation(
            twin_b.initial_state, twin_b.physics_params, FluidType.RL, vol, duration
        )
        
        leak_a = res_a['fluid_leaked_percentage']
        leak_b = res_b['fluid_leaked_percentage']
        
        print(f"Standard Leak: {leak_a}% of infused volume")
        print(f"Dengue Leak:   {leak_b}% of infused volume")
        
        # Dengue patient MUST leak significantly more
        self.assertTrue(leak_b > leak_a * 1.5, "Dengue patient did not leak significantly more than standard patient")

    def test_02_sam_heart_failure(self):
        """
        SCENARIO: Does a SAM child develop edema faster?
        FIX: We start with WELL-HYDRATED patients to test overfill compliance immediately.
        """
        print("\nCLINICAL TEST 2: SAM Fragility (Edema Risk)")
        
        # Patient A: Normal Nutrition, Well Hydrated (Diagnosis=Unknown -> No Deficit)
        data_normal = self.create_base_patient(ClinicalDiagnosis.UNKNOWN, weight=10, muac=15)
        twin_normal = PediaFlowPhysicsEngine.create_digital_twin(data_normal)
        
        # Patient B: SAM, Well Hydrated (Diagnosis=Unknown -> No Deficit)
        data_sam = self.create_base_patient(ClinicalDiagnosis.UNKNOWN, weight=10, muac=10.5)
        twin_sam = PediaFlowPhysicsEngine.create_digital_twin(data_sam)
        
        # Give Aggressive Fluid Challenge (20ml/kg in 20 mins)
        # Since they start full, this goes straight to overload
        vol = 200; duration = 20
        
        res_normal = PediaFlowPhysicsEngine.run_simulation(
            twin_normal.initial_state, twin_normal.physics_params, FluidType.RL, vol, duration
        )
        res_sam = PediaFlowPhysicsEngine.run_simulation(
            twin_sam.initial_state, twin_sam.physics_params, FluidType.RL, vol, duration
        )
        
        p_inter_normal = res_normal['final_state'].p_interstitial_mmHg
        p_inter_sam = res_sam['final_state'].p_interstitial_mmHg
        
        print(f"Normal Lung Pressure: {p_inter_normal:.2f} mmHg")
        print(f"SAM Lung Pressure:    {p_inter_sam:.2f} mmHg")
        
        # SAM child has compliance=50, Normal=100.
        # So SAM pressure should rise roughly 2x faster for the same volume excess.
        self.assertTrue(p_inter_sam > p_inter_normal, "SAM patient did not develop higher pressure than normal patient")

    def test_03_renal_shutdown(self):
        """
        SCENARIO: If a child is anuric (AKI), does the fluid just pile up?
        """
        print("\nCLINICAL TEST 3: Renal Shutdown (AKI)")
        
        data = self.create_base_patient(ClinicalDiagnosis.SEPTIC_SHOCK)
        data['time_since_last_urine_hours'] = 12.0 # Deep AKI
        
        twin = PediaFlowPhysicsEngine.create_digital_twin(data)
        
        # Give 200ml
        res = PediaFlowPhysicsEngine.run_simulation(
            twin.initial_state, twin.physics_params, FluidType.NS, 200, 60
        )
        
        urine_output = res['final_state'].q_urine_ml_min
        print(f"Urine Output in AKI: {urine_output:.4f} ml/min")
        
        # Urine should be effectively zero
        self.assertAlmostEqual(urine_output, 0.0, places=2, msg="Anuric patient is making too much urine")

    def test_04_third_space_losses(self):
        """
        SCENARIO: Ongoing Diarrhea ("The Third Vector").
        If we give maintenance fluid but child has severe diarrhea, do they net zero?
        """
        print("\nCLINICAL TEST 4: Ongoing Losses (Diarrhea)")
        
        data = self.create_base_patient(ClinicalDiagnosis.SEVERE_DEHYDRATION)
        data['ongoing_losses_severity'] = OngoingLosses.SEVERE # 10 ml/kg/hr loss
        
        twin = PediaFlowPhysicsEngine.create_digital_twin(data)
        
        # Give Maintenance (4ml/kg/hr) -> 40ml/hr
        # Loss is 10ml/kg/hr -> 100ml/hr
        # Net balance should be negative (-60ml)
        
        res = PediaFlowPhysicsEngine.run_simulation(
            twin.initial_state, twin.physics_params, FluidType.RL, 40, 60
        )
        
        final_vol = res['final_state'].v_blood_current_l
        start_vol = twin.initial_state.v_blood_current_l
        
        print(f"Start Blood Vol: {start_vol:.3f} L")
        print(f"End Blood Vol:   {final_vol:.3f} L")
        
        self.assertTrue(final_vol < start_vol, "Patient gained volume despite severe diarrhea > intake")

if __name__ == '__main__':
    unittest.main()
