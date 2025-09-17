# serializers.py
from rest_framework import serializers

# -----------------------------
# Canonical choices (single source of truth)
# -----------------------------
GENDER_CHOICES = ['M', 'F']
SMOKING_CHOICES = ['never', 'former', 'current']
ALCOHOL_CHOICES = ['none', 'social', 'heavy']

CYP_PHENOS = ['PM', 'IM', 'NM', 'RM']
UGT1A9_FUNC = ['decreased', 'normal', 'increased']
RYR1_STATUS = ['Normal', 'Variant']

# PD genetics (canonical rsIDs used by your engine)
GABRA1_CHOICES = ['rs4263535:G/G', 'rs4263535:A/G', 'rs4263535:A/A']
COMT_CHOICES = ['Val158Met:Met/Met', 'Val158Met:Val/Met', 'Val158Met:Val/Val']
OPRM1_CHOICES = ['A118G:G/G', 'A118G:A/G', 'A118G:A/A']
CACNA1C_CHOICES = ['rs1006737:A/A', 'rs1006737:A/G', 'rs1006737:G/G']

# Input alias map for legacy/front-end variants → canonical keys
# Accept rs2279020:* and normalize to rs4263535:* (your PD table key)
GABRA1_ALIASES = {
    'rs2279020:AA': 'rs4263535:A/A',
    'rs2279020:AG': 'rs4263535:A/G',
    'rs2279020:GG': 'rs4263535:G/G',
    # Accept lower/upper/mixed just in case
    'rs2279020:aa': 'rs4263535:A/A',
    'rs2279020:ag': 'rs4263535:A/G',
    'rs2279020:gg': 'rs4263535:G/G',
}


class PatientDataSerializer(serializers.Serializer):
    """
    Serializer for patient data containing all evidence-based parameters
    for anesthesia induction decision support.
    """

    # Demographics
    age = serializers.IntegerField(
        min_value=18, max_value=95, required=True, help_text="Age in years")
    weight_kg = serializers.FloatField(
        min_value=30, max_value=220, required=True, help_text="Weight in kilograms")
    height_cm = serializers.FloatField(
        min_value=120, max_value=220, required=True, help_text="Height in centimeters")
    gender = serializers.ChoiceField(
        choices=GENDER_CHOICES, required=True, help_text="Gender (M/F)")

    # Clinical factors
    asa_class = serializers.IntegerField(
        min_value=1, max_value=5, required=False,
        help_text="ASA Physical Status (1-5) - calculated automatically")
    cardiovascular_disease = serializers.BooleanField(
        required=True, help_text="Presence of cardiovascular disease")
    heart_failure = serializers.BooleanField(
        required=True, help_text="Presence of heart failure")
    reactive_airway = serializers.BooleanField(
        required=True, help_text="Reactive airway disease")
    copd = serializers.BooleanField(
        required=True, help_text="Chronic obstructive pulmonary disease")
    diabetes = serializers.BooleanField(
        required=True, help_text="Diabetes mellitus")
    hypertension = serializers.BooleanField(
        required=True, help_text="Hypertension")
    smoking_status = serializers.ChoiceField(
        choices=SMOKING_CHOICES, required=True, help_text="Smoking status")
    alcohol_use = serializers.ChoiceField(
        choices=ALCOHOL_CHOICES, required=True, help_text="Alcohol use pattern")

    # PK genetics
    ryr1_variant = serializers.ChoiceField(
        choices=RYR1_STATUS, required=True, help_text="RYR1 variant status for MH risk")
    cyp2b6 = serializers.ChoiceField(
        choices=CYP_PHENOS, required=True, help_text="CYP2B6 metabolizer status")
    ugt1a9 = serializers.ChoiceField(
        choices=UGT1A9_FUNC, required=True, help_text="UGT1A9 glucuronidation function")
    cyp3a4 = serializers.ChoiceField(
        choices=CYP_PHENOS, required=True, help_text="CYP3A4 metabolizer status")
    cyp2c9 = serializers.ChoiceField(
        choices=CYP_PHENOS, required=True, help_text="CYP2C9 metabolizer status")

    # PD genetics (engine expects canonical rsIDs in PD tables)
    gabra1 = serializers.ChoiceField(
        choices=GABRA1_CHOICES, required=True, help_text="GABRA1 receptor sensitivity variant")
    comt = serializers.ChoiceField(
        choices=COMT_CHOICES, required=True, help_text="COMT stress response variant")
    oprm1 = serializers.ChoiceField(
        choices=OPRM1_CHOICES, required=True, help_text="OPRM1 opioid receptor sensitivity")
    cacna1c = serializers.ChoiceField(
        choices=CACNA1C_CHOICES, required=True, help_text="CACNA1C calcium channel variant")

    # Procedure
    procedure_duration_min = serializers.IntegerField(
        min_value=1, max_value=1440, required=True, help_text="Procedure duration in minutes")
    neuromonitoring = serializers.BooleanField(
        required=True, help_text="Whether neuromonitoring is required")

    # Options
    include_dose_response_image = serializers.BooleanField(
        default=False, help_text="Include dose-response curve image in response")

    # -------------- Input normalization --------------
    def to_internal_value(self, data):
        """
        Normalize legacy inputs BEFORE core validation:
        - GABRA1 aliases (rs2279020:* → rs4263535:*)
        - Default GABRB2 if omitted/null
        - Minor casing guard for gender/smoking/alcohol
        """
        data = dict(data) if isinstance(data, dict) else data

        # Normalize GABRA1 aliases
        g1 = data.get('gabra1')
        if isinstance(g1, str):
            alias = GABRA1_ALIASES.get(g1) or GABRA1_ALIASES.get(g1.strip())
            if alias:
                data['gabra1'] = alias

        # Normalize case for categorical strings that UI might send in mixed case
        for k in ('gender', 'smoking_status', 'alcohol_use'):
            v = data.get(k)
            if isinstance(v, str):
                data[k] = v.strip()
                # normalize some common variations
                if k == 'gender':
                    if v.lower().startswith('m'):
                        data[k] = 'M'
                    elif v.lower().startswith('f'):
                        data[k] = 'F'

        return super().to_internal_value(data)

    # -------------- Cross-field validation --------------
    def validate(self, data):
        """Cross-field sanity checks."""
        weight_kg = data.get('weight_kg')
        height_cm = data.get('height_cm')
        if weight_kg and height_cm:
            bmi = weight_kg / ((height_cm / 100) ** 2)
            if bmi < 10 or bmi > 80:
                raise serializers.ValidationError(
                    "BMI is unrealistic. Check weight/height.")

        # Age guard (redundant with field min, but explicit message)
        age = data.get('age')
        if age and age < 18:
            raise serializers.ValidationError(
                "Age must be ≥18 for this model.")

        return data


class AnesthesiaPlanResponseSerializer(serializers.Serializer):
    """
    Serializer for the anesthesia plan response.
    Keep non-guaranteed sections optional (required=False) to avoid serialization errors
    when certain branches (e.g., agent not feasible) are legitimately absent.
    """
    patient_summary = serializers.DictField(
        help_text="Summary of patient data")
    timestamp = serializers.CharField(help_text="Timestamp of calculation")
    evidence_based = serializers.BooleanField(help_text="Evidence-based flag")

    route_selection = serializers.DictField(
        help_text="Route selection analysis and results")
    agent_selection = serializers.DictField(
        help_text="Agent selection analysis and results", required=False)
    dose_calculation = serializers.DictField(
        help_text="Dose calculation with adjustments", required=False)
    risk_prediction = serializers.DictField(
        help_text="Risk prediction and therapeutic window analysis", required=False)
    evidence_summary = serializers.DictField(
        help_text="Summary of all evidence sources used", required=False)
