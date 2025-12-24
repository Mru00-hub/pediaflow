import unittest
from core_physics import PediaFlowPhysicsEngine
from models import (
    PatientInput, 
    ClinicalDiagnosis, 
    OngoingLosses
)
from constants import FluidType

class TestStressLimits(unittest.TestCase):
    
    def setUp(self):
        # Standard 10kg child
        self.base_patient = {
            'age_months': 24, 'weight_kg': 10.0, 'sex': 'M', 'muac_cm': 14.0,
            'temp_celsius': 37.0, 'hemoglobin_g_dl': 10.0, 'systolic_bp': 90,
            'heart_rate': 110, 'capillary_refill_sec': 2, 'sp_o2_percent': 98,
            'respiratory_rate_bpm': 30, 'current_sodium': 140, 'current_glucose': 90,
            'hematocrit_pct': 30.0, 'diagnosis': ClinicalDiagnosis.UNKNOWN, 'illness_day': 1
        }

    def test_01_the_bleeding_paradox(self):
        """
        CRITIQUE: Your engine assumes 'Ongoing Losses' are always water/electrolytes (Diarrhea).
        SCENARIO: If a child is bleeding (Whole Blood Loss), Hct should stay same or drop.
        FAILURE MODE: If Hct RISES, your engine cannot simulate Trauma/Hemorrhage.
        """
        print("\nSTRESS TEST 1: The Bleeding Paradox")
        
        # Simulate "Severe Loss" (10ml/kg/hr)
        # In Trauma, this is bleeding. In your engine, this is... ?
        data = self.base_patient.copy()
        data['ongoing_losses_severity'] = OngoingLosses.SEVERE
        twin = PediaFlowPhysicsEngine.create_digital_twin(data)
        
        # Run for 2 hours with NO fluid (pure loss)
        res = PediaFlowPhysicsEngine.run_simulation(
            twin.initial_state, twin.physics_params, FluidType.RL, 0, 120
        )
        
        start_hct = twin.initial_state.current_hematocrit_dynamic
        end_hct = res['final_state'].current_hematocrit_dynamic
        
        print(f"Start Hct: {start_hct}")
        print(f"End Hct:   {end_hct:.2f}")
        
        # If Hct went UP, the engine removed plasma but kept Red Cells.
        # This is correct for Diarrhea, but FATAL for Bleeding logic.
        if end_hct > start_hct:
            print(">> CRITIQUE: Engine treats ALL loss as Diarrhea (Hemoconcentration).")
            print(">> LIMITATION: Cannot use for Trauma/Hemorrhage patients.")
        else:
            print(">> SURPRISE: Engine handled bleeding correctly.")

    def test_02_the_salt_block_kidney(self):
        """
        CRITIQUE: You track Sodium Input, but do you track Sodium Output?
        SCENARIO: Give high Sodium fluid for 24 hours.
        FAILURE MODE: If Total Sodium Load is massive but Urine is high, 
        the net load should be balanced. If you only count UP, you flag false alarms.
        """
        print("\nSTRESS TEST 2: The Salt Block Kidney")
        
        twin = PediaFlowPhysicsEngine.create_digital_twin(self.base_patient)
        
        # Run 24 hours of Normal Saline (154 mEq/L) at maintenance
        # Input: ~400ml -> ~60 mEq Sodium
        res = PediaFlowPhysicsEngine.run_simulation(
            twin.initial_state, twin.physics_params, FluidType.NS, 400, 1440
        )
        
        final_na_load = res['final_state'].total_sodium_load_meq
        
        print(f"Total Na Infused: {final_na_load:.1f} mEq")
        print(">> CRITIQUE: Did the kidneys excrete any of this?")
        
        # Real kidneys excrete sodium. Does your model subtract from 'total_sodium_load_meq'?
        # Looking at your code: You only ADD to it.
        # failure: The engine tracks "Load Administered", not "Net Body Load".
        # This will trigger False Positive Cerebral Edema alerts on long runs.
        self.assertTrue(final_na_load > 0, "Sodium load tracking broken")

    def test_03_the_frozen_heart(self):
        """
        CRITIQUE: Does 'Afterload Sensitivity' actually work?
        SCENARIO: Two identical babies given fluid. One is 37C, one is 33C (Hypothermia).
        FAILURE MODE: The Cold baby should respond POORLY to volume (High SVR fights the weak heart).
        """
        print("\nSTRESS TEST 3: The Frozen Heart (Afterload Mismatch)")
        
        # Warm Baby
        data_warm = self.base_patient.copy()
        twin_warm = PediaFlowPhysicsEngine.create_digital_twin(data_warm)
        
        # Cold Baby
        data_cold = self.base_patient.copy()
        data_cold['temp_celsius'] = 33.0 # Severe Hypothermia
        twin_cold = PediaFlowPhysicsEngine.create_digital_twin(data_cold)
        
        # Give Bolus
        vol = 200; duration = 20
        res_warm = PediaFlowPhysicsEngine.run_simulation(
            twin_warm.initial_state, twin_warm.physics_params, FluidType.RL, vol, duration
        )
        res_cold = PediaFlowPhysicsEngine.run_simulation(
            twin_cold.initial_state, twin_cold.physics_params, FluidType.RL, vol, duration
        )
        
        map_rise_warm = res_warm['predicted_map_rise']
        map_rise_cold = res_cold['predicted_map_rise']
        
        print(f"Warm MAP Rise: +{map_rise_warm}")
        print(f"Cold MAP Rise: +{map_rise_cold}")
        
        # The Cold baby has Higher SVR (Vasoconstriction) -> Initially MAP might rise MORE?
        # OR: The Cold baby has 'afterload_sensitivity' -> Cardiac Output drops -> MAP rises LESS?
        # This tests the complex interaction of your physics formulas.
        
        if map_rise_cold > map_rise_warm:
             print(">> OBSERVATION: Vasoconstriction dominated (High SVR raised BP).")
        else:
             print(">> OBSERVATION: Afterload Sensitivity dominated (Weak heart failed against resistance).")

if __name__ == '__main__':
    unittest.main()
