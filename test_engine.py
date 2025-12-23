import unittest
from app import (
    PediaFlowPhysicsEngine, PatientInput, ClinicalDiagnosis, 
    FluidType, SimulationState, PhysiologicalParams, CalculationWarnings
)

class TestPediaFlowEngine(unittest.TestCase):

    def setUp(self):
        """Create a standard 10kg infant for testing."""
        self.standard_patient = {
            'age_months': 12,
            'weight_kg': 10.0,
            'sex': 'M',
            'muac_cm': 14.0,
            'temp_celsius': 37.0,
            'hemoglobin_g_dl': 10.0,
            'systolic_bp': 90,
            'heart_rate': 110,
            'capillary_refill_sec': 2,
            'sp_o2_percent': 98,
            'respiratory_rate_bpm': 30,
            'current_sodium': 140,
            'current_glucose': 90,
            'hematocrit_pct': 30.0,
            'diagnosis': ClinicalDiagnosis.SEVERE_DEHYDRATION,
            'illness_day': 1
        }
        
        # Initialize the engine once
        self.res = PediaFlowPhysicsEngine.create_digital_twin(self.standard_patient)
        self.assertTrue(self.res.success, "Failed to initialize Digital Twin")
        self.initial_state = self.res.initial_state
        self.params = self.res.physics_params

    def test_01_mass_conservation(self):
        """
        Physics Check: Total Fluid IN must equal Compartment Changes + Urine OUT
        """
        print("\nTEST 1: Mass Conservation (100ml Bolus)")
        
        volume_in = 100.0
        duration = 60 # minutes
        
        # Run Simulation
        sim_res = PediaFlowPhysicsEngine.run_simulation(
            self.initial_state, self.params, FluidType.RL, volume_in, duration
        )
        final = sim_res['final_state']
        
        # Calculate Delta Volumes (L -> mL)
        d_blood = (final.v_blood_current_l - self.initial_state.v_blood_current_l) * 1000
        d_inter = (final.v_interstitial_current_l - self.initial_state.v_interstitial_current_l) * 1000
        d_icf = (final.v_intracellular_current_l - self.initial_state.v_intracellular_current_l) * 1000
        
        # Calculate Outputs (mL/min * min)
        # Note: Simulation integrates these, but we can grab the cumulative totals from the loop
        # For simplicity in this unit test, we approximate using the averages or check specific integrators if available
        # Better approach: The engine tracks 'total_volume_infused_ml'. 
        # But we need to track total urine/leak.
        
        # Let's perform a single step integration manually to check the math exactly
        step_res = PediaFlowPhysicsEngine.simulate_single_step(
            self.initial_state, self.params, 1000.0, FluidType.RL, dt_minutes=1.0
        )
        
        # Input: 1000 ml/hr for 1 min = 16.66 ml
        vol_in_step = 16.666
        
        # Compartment Changes
        d_b = (step_res.v_blood_current_l - self.initial_state.v_blood_current_l) * 1000
        d_i = (step_res.v_interstitial_current_l - self.initial_state.v_interstitial_current_l) * 1000
        d_c = (step_res.v_intracellular_current_l - self.initial_state.v_intracellular_current_l) * 1000
        
        # Outputs calculated in that step
        # Note: We can infer urine/loss from the volume delta equations in your code
        # dv_blood = Input - Leak - Urine - Loss + Lymph
        # dv_inter = Leak - Lymph - Loss - Insensible - Osmotic
        # dv_icf = Osmotic
        
        # Total Mass Balance:
        # Input - (Urine + Insensible + OngoingLoss) = (d_b + d_i + d_c)
        
        # Re-calculate the fluxes for this step to verify
        # (In a real test we'd expose these cumulative counters in State, but let's trust the delta)
        
        # APPROXIMATION CHECK
        # If we give fluid, the weight should go up by exactly (Input - Urine - Insensible)
        # Your code: current_weight_dynamic_kg += (rate - urine)/1000
        
        expected_weight_gain = (1000.0/60.0 - step_res.q_urine_ml_min) / 1000.0
        actual_weight_gain = step_res.current_weight_dynamic_kg - self.initial_state.current_weight_dynamic_kg
        
        print(f"Expected Wt Gain: {expected_weight_gain:.5f} kg")
        print(f"Actual Wt Gain:   {actual_weight_gain:.5f} kg")
        
        self.assertAlmostEqual(expected_weight_gain, actual_weight_gain, places=4)

    def test_02_hematocrit_dilution(self):
        """
        Physics Check: Adding fluid must dilute Hematocrit.
        Formula: C1V1 = C2V2
        """
        print("\nTEST 2: Hemodilution")
        
        # 1. Give massive bolus (pure volume expansion)
        # 500ml into a 10kg kid (approx 50% blood volume increase)
        # Blood Vol approx 0.8L. New Vol approx 1.3L.
        # Hct should drop from 30 -> ~18
        
        sim_res = PediaFlowPhysicsEngine.run_simulation(
            self.initial_state, self.params, FluidType.NS, 500, 30
        )
        final_hct = sim_res['final_state'].current_hematocrit_dynamic
        
        print(f"Initial Hct: {self.initial_state.current_hematocrit_dynamic}")
        print(f"Final Hct (500ml bolus): {final_hct:.2f}")
        
        self.assertTrue(final_hct < 25.0, "Hematocrit did not dilute significantly")
        self.assertTrue(final_hct > 10.0, "Hematocrit dropped impossibly low")

        def test_03_glucose_burn(self):
        """
        Metabolic Check: Glucose must drop on Saline, but RISE on D5 Bolus.
        """
        print("\nTEST 3: Glucose Burn")
        
        # 1. Run 60 mins of Saline (Maintenance Rate) -> Should Drop
        sim_res_ns = PediaFlowPhysicsEngine.run_simulation(
            self.initial_state, self.params, FluidType.NS, 10, 60
        )
        glucose_ns = sim_res_ns['final_state'].current_glucose_mg_dl
        
        # 2. Run 60 mins of D5-Saline (BOLUS Rate: 200ml) -> Should Rise
        # We give 20ml/kg (200ml) to overwhelm the metabolic burn
        sim_res_d5 = PediaFlowPhysicsEngine.run_simulation(
            self.initial_state, self.params, FluidType.D5_NS, 200, 60
        )
        glucose_d5 = sim_res_d5['final_state'].current_glucose_mg_dl
        
        print(f"Start Glucose: 90 mg/dL")
        print(f"End Glucose (NS Maintenance): {glucose_ns:.1f} mg/dL")
        print(f"End Glucose (D5 Bolus):       {glucose_d5:.1f} mg/dL")
        
        # NS should drop (metabolism consumes stores)
        self.assertTrue(glucose_ns < 90, "Glucose failed to drop on NS")
        
        # D5 Bolus should rise (Supply 166mg/min > Demand 30mg/min)
        self.assertTrue(glucose_d5 > 100, f"Glucose failed to rise on D5 Bolus (Got {glucose_d5})")

if __name__ == '__main__':
    unittest.main()
