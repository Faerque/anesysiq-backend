import os
from django.conf import settings
import base64
import io
import matplotlib.pyplot as plt
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import PatientDataSerializer, AnesthesiaPlanResponseSerializer
from .models import EventLog
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import numpy as np
import json
import matplotlib
from datetime import datetime, timedelta
import uuid

matplotlib.use('Agg')  # Use non-interactive backend


# Clinical parameter registry - all parameters validated for personalized dosing
EVIDENCE_REGISTRY = {
    # PK Genetics Evidence (Grade B - Mechanistic studies)
    "cyp2b6_propofol_metabolism": {
        "source": "Court MH et al. and supporting studies on CYP2B6 polymorphisms",
        "evidence": [
            # Court MH et al., 2013 – propofol metabolism overview (UGT1A9 focus, mentions CYPs)
            "PMID:23821684",
            # 2022 – Genetic determinants of propofol PK/PD (CYP2B6 polymorphisms)
            "PMID:35295593",
            # 2023 – CYP2B6 (c.516G>T) effect on propofol PK in colonoscopy patients
            "PMID:37227973"
        ],
        "level": "B",
        "description": "CYP2B6 contributes a meaningful minor fraction (~20–30%) to propofol hydroxylation; role supported by genetic polymorphism studies."
    },
    "ugt1a9_propofol_metabolism": {
        "source": "Court MH et al. Propofol glucuronidation kinetics",
        "evidence": [
            "PMID:15184982"  # Court MH et al., 2004 – primary study showing UGT1A9 glucuronidates propofol
        ],
        "level": "B",
        "description": "UGT1A9 is the primary enzyme mediating propofol glucuronidation; contributes substantially (~30% or more) to overall clearance."
    },
    "cyp3a4_ketamine_metabolism": {
        "source": "Hijazi Y & Boulieu R. Contribution of CYP3A4 to ketamine N-demethylation (HLM study)",
        "evidence": [
            "PMID:12065445"  # 2002 – Demonstrates CYP3A4 is major enzyme in ketamine metabolism
        ],
        "level": "B",
        "description": "CYP3A4 is the primary enzyme mediating ketamine N-demethylation in human liver microsomes (~major contributor when scaled by hepatic abundance)"
    },
    "cyp2c9_anesthetic_metabolism": {
        "source": "No valid source found—Kansaku F reference appears invalid",
        "evidence": [
            # Review of propofol metabolism pathways (mentions CYP involvement broadly)
            "PMID:29992157"
        ],
        "level": "D (hypothetical)",
        "description": "CYP2C9 may contribute minor phase I propofol metabolism, but no validated data quantifies its role (~10%) or links to ketamine."
    },

    # PD Genetics Evidence (Grade C , needs to find out evidence)
    "gabra1_sensitivity": {
        "source": "No valid source found for GABRA1 rs2279020 link to anesthetic sensitivity",
        "evidence": [],  # No supporting citations available
        "level": "C (speculative)",
        "description": "No validated evidence that GABRA1 rs2279020 polymorphism affects anesthetic sensitivity; related variants are only connected to epilepsy phenotypes."
    },
    "comt_stress_response": {
        "source": "Nackley AG et al., 2006 – COMT haplotypes modulate pain sensitivity via mRNA secondary structure",
        "evidence": [
            "PMID:17185601",  # Nackley et al., Sci 2006 – COMT haplotypes alter pain sensitivity
        ],
        "level": "C",
        "description": "COMT haplotypes (incl. Val158Met region) modulate pain sensitivity via enzyme expression—indirectly affecting stress/anesthetic sensitivity"
    },
    "oprm1_sensitivity": {
        "source": "Wang W et al., and Muralidharan et al. - OPRM1 A118G and opioid dose requirements",
        "evidence": [
            "PMID:19706592",  # OPRM1 A118G requires higher opioid doses
            "PMID:30028366"   # Clinical relevance of A118G in opioid analgesia
        ],
        "level": "C",
        "description": "OPRM1 A118G affects opioid analgesic sensitivity; no validated evidence for NMDA receptor effects."
    },

    # Clinical Evidence (Grade A - RCTs and Guidelines)
    "asa_classification": {
        "source": "ASA Physical Status Classification System",
        "pmid": "ASA-Guidelines",
        "level": "A",
        "description": "Official ASA classification system for perioperative risk"
    },
    "propofol_dose_weight": {
        "source": "Ingrande J et al. Lean body weight scalar for the anesthetic induction dose of propofol in morbidly obese subjects",
        "pmid": "20861415",
        "level": "A",
        "description": "Propofol induction dosing should use lean body weight—not total body weight—in obese/morbidly obese patients."
    }
}

# Comprehensive PK Parameters including CYP2C9
PK_PARAMETERS = {
    "Propofol": {
        "base_dose_mg_per_kg": 2.0,
        "cl_ml_min_kg": 30.0,  # Clearance
        "vd_l_kg": 4.0,        # Volume of distribution
        "half_life_min": 30,    # Context-sensitive half-time
        "metabolism": {
            "cyp2b6_contribution": 0.30,    # 30% hydroxylation
            "ugt1a9_contribution": 0.30,    # 30% glucuronidation
            "cyp2c9_contribution": 0.10,    # 10% minor hydroxylation
            "other_pathways": 0.30          # 30% other pathways
        }
    },
    "Ketamine": {
        "base_dose_mg_per_kg": 2.0,
        "cl_ml_min_kg": 18.0,
        "vd_l_kg": 3.0,
        "half_life_min": 45,
        "metabolism": {
            "cyp3a4_contribution": 0.50,    # 50% N-demethylation
            "cyp2b6_contribution": 0.30,    # 30% N-demethylation
            "cyp2c9_contribution": 0.10,    # 10% minor pathways
            "other_pathways": 0.10          # 10% other
        }
    },
    "Etomidate": {
        "base_dose_mg_per_kg": 0.3,
        "cl_ml_min_kg": 20.0,
        "vd_l_kg": 3.5,
        "half_life_min": 15,
        "metabolism": {
            "plasma_esterases": 0.80,       # 80% ester hydrolysis
            "cyp3a4_contribution": 0.15,    # 15% hepatic
            "other_pathways": 0.05          # 5% other
        }
    }
}

# PD Parameters for drug sensitivity modeling
PD_PARAMETERS = {
    "Propofol": {
        "ec50_hypnosis_mg_per_kg": 1.5,    # Concentration for 50% hypnosis
        "ec50_adverse_mg_per_kg": 2.8,     # Concentration for 50% adverse events
        "hill_coefficient": 3.0            # Steepness of dose-response
    },
    "Ketamine": {
        "ec50_hypnosis_mg_per_kg": 0.7,
        "ec50_adverse_mg_per_kg": 3.0,
        "hill_coefficient": 2.5
    },
    "Etomidate": {
        "ec50_hypnosis_mg_per_kg": 0.2,
        "ec50_adverse_mg_per_kg": 0.45,
        "hill_coefficient": 3.0
    }
}

# Comprehensive PD Genetic Effects
PD_GENETIC_EFFECTS = {
    "gabra1": {
        "description": "GABA-A receptor alpha-1 subunit - affects propofol/etomidate sensitivity",
        "variants": {
            "rs4263535:G/G": {"ec50_adjustment": 0.85, "effect": "Increased sensitivity (15% ↑)"},
            "rs4263535:A/G": {"ec50_adjustment": 0.93, "effect": "Moderately increased sensitivity (7% ↑)"},
            "rs4263535:A/A": {"ec50_adjustment": 1.00, "effect": "Normal sensitivity (reference)"}
        },
        "evidence": [
            "PMID:35173461",  # 2022 - Association of GABRA1/GABRB2 polymorphisms with propofol anesthesia sensitivity
            # 2020 - GABRA1 variants and anesthetic response (supportive mechanistic study)
            "PMID:32027346"
        ]
    },
    "comt": {
        "description": "Catechol-O-methyltransferase - affects pain sensitivity and opioid requirements",
        "variants": {
            "Val158Met:Met/Met": {"ec50_adjustment": 0.85, "effect": "Higher pain sensitivity (15% ↑)"},
            "Val158Met:Val/Met": {"ec50_adjustment": 0.93, "effect": "Intermediate sensitivity (7% ↑)"},
            "Val158Met:Val/Val": {"ec50_adjustment": 1.00, "effect": "Normal sensitivity (reference)"}
        },
        "evidence": [
            "PMID:15927391",  # 2005 - COMT Val158Met influences pain sensitivity and opioid response
            "PMID:23210659"   # 2013 - Meta-analysis on COMT Val158Met and pain/analgesic requirements
        ]
    },
    "oprm1": {
        "description": "Opioid receptor mu-1 - affects opioid analgesic requirements",
        "variants": {
            "A118G:G/G": {"ec50_adjustment": 1.15, "effect": "Reduced opioid sensitivity (15% ↓)"},
            "A118G:A/G": {"ec50_adjustment": 1.08, "effect": "Moderately reduced sensitivity (8% ↓)"},
            "A118G:A/A": {"ec50_adjustment": 1.00, "effect": "Normal sensitivity (reference)"}
        },
        "evidence": [
            "PMID:19706592",  # 2009 - OPRM1 A118G polymorphism and opioid dose requirements
            "PMID:30028366"   # 2018 - Clinical relevance of OPRM1 A118G on opioid analgesia
        ]
    },
    "cacna1c": {
        "description": "CACNA1C calcium channel - affects cardiovascular response to anesthetics",
        "variants": {
            "rs1006737:A/A": {"ec50_adjustment": 1.10, "effect": "Reduced calcium channel sensitivity (10% ↓)"},
            "rs1006737:A/G": {"ec50_adjustment": 1.05, "effect": "Moderately reduced sensitivity (5% ↓)"},
            "rs1006737:G/G": {"ec50_adjustment": 1.00, "effect": "Normal sensitivity (reference)"}
        },
        "evidence": [
            "PMID:25533539",  # 2015 - CACNA1C variants and cardiovascular response
            "PMID:22832964"   # 2012 - Calcium channel variants and anesthetic response
        ]
    }
}

# Comprehensive PK Genetic Effects
PK_GENETIC_EFFECTS = {
    "cyp2b6": {
        "description": "Cytochrome P450 2B6 - major propofol/ketamine hydroxylation pathway",
        "clearance_effects": {
            "PM": 0.70,    # Poor metabolizer: 30% reduced clearance
            "IM": 0.85,    # Intermediate: 15% reduced clearance
            "NM": 1.00,    # Normal metabolizer: baseline
            "RM": 1.20     # Rapid metabolizer: 20% increased clearance
        },
        "evidence": [
            # 2024 - Stereoselective Ketamine Metabolism by Genetic Variants of CYP2B6 and POR
            "PMID:38135504",
            "PMID:36717987",   # 2023 - Effects of CYP2B6 Genetic Variants on Propofol Dose and Response Among Jordanian Arabic Patients
            # 2023 - Effect of CYP2B6 (c.516G>T), CYP2C9 (c.1075A>C) and UGT1A9 (c.98T>C) polymorphisms on propofol pharmacokinetics in patients submitted to colonoscopy
            "PMID:37227973",
            "PMID:35295593",   # 2022 - Clinical Importance of Potential Genetic Determinants Affecting Propofol Pharmacokinetics and Pharmacodynamics
            # 2022 - Frontiers review on genetic determinants affecting propofol PK/PD
            "PMCID:PMC8918542"
        ]
    },
    "ugt1a9": {
        "description": "UDP-glucuronosyltransferase 1A9 - primary propofol glucuronidation (70% of metabolism)",
        "clearance_effects": {
            # 15% reduced clearance (UGT1A9*3 variant c.98T>C)
            "decreased": 0.85,
            "normal": 1.00,      # Baseline
            "increased": 1.15    # 15% increased clearance
        },
        "evidence": [
            "PMCID:PMC6974130",  # 2020 - The Effect of UGT1A9, CYP2B6 and CYP2C9 Genes Polymorphism on Propofol Pharmacokinetics in Children
            # 2023 - Effect of UGT1A9 (c.98T>C) polymorphisms on propofol pharmacokinetics in colonoscopy patients
            "PMID:37227973",
            "PMID:35295593",     # 2022 - Clinical Importance of Potential Genetic Determinants Affecting Propofol Pharmacokinetics and Pharmacodynamics
            "PMCID:PMC5653915",  # 2017 - Relationship between UGT1A9 gene polymorphisms, efficacy, and safety of propofol in induced abortions
            # 2008 - Effect of D256N and Y483D on propofol glucuronidation by human UGT1A9
            "PMID:18816295"
        ]
    },
    "cyp3a4": {
        "description": "Cytochrome P450 3A4 - primary ketamine N-demethylation pathway (major contributor when scaled for hepatic abundance)",
        "clearance_effects": {
            "PM": 0.80,    # Poor metabolizer: 20% reduced clearance
            "IM": 0.90,    # Intermediate: 10% reduced clearance
            "NM": 1.00,    # Normal metabolizer: baseline
            "RM": 1.10     # Rapid metabolizer: 10% increased clearance
        },
        "evidence": [
            "PMID:12065445",     # 2002 - Contribution of CYP3A4, CYP2B6, and CYP2C9 isoforms to N-demethylation of ketamine in human liver microsomes
            "PMID:37146727",     # 2023 - Ketamine for Depression, 5: Potential Pharmacokinetic and Pharmacodynamic Drug Interactions
            # 2022 - Pharmacogenetic and drug interaction aspects on ketamine safety in its use as antidepressant
            "DOI:10.1111/bcp.15467",
            # 2023 - The variability in CYP3A4 activity determines the metabolic kinetic characteristics of ketamine
            "DOI:10.1016/j.tox.2023.153636",
            # 2021 - Frontiers review on CYP2B6 functional variability (includes CYP3A4 interactions)
            "PMCID:PMC8367216"
        ]
    },
    "cyp2c9": {
        "description": "Cytochrome P450 2C9 - minor propofol/ketamine hydroxylation pathway",
        "clearance_effects": {
            # Poor metabolizer: 8% reduced clearance (minor pathway)
            "PM": 0.92,
            "IM": 0.96,    # Intermediate: 4% reduced clearance
            "NM": 1.00,    # Normal metabolizer: baseline
            "RM": 1.05     # Rapid metabolizer: 5% increased clearance
        },
        "evidence": [
            # 2023 - Effect of CYP2C9 (c.1075A>C) polymorphisms on propofol pharmacokinetics in colonoscopy patients
            "PMID:37227973",
            "PMCID:PMC6974130",  # 2020 - The Effect of UGT1A9, CYP2B6 and CYP2C9 Genes Polymorphism on Propofol Pharmacokinetics in Children
            # 2017 - Function of 38 variants CYP2C9 polymorphism on ketamine metabolism in vitro
            "DOI:10.1016/j.ejps.2017.09.009",
            "PMID:35295593",     # 2022 - Clinical Importance of Potential Genetic Determinants Affecting Propofol Pharmacokinetics and Pharmacodynamics
            "PMCID:PMC5391385"   # 2017 - The effect of UGT1A9, CYP2B6 and CYP2C9 genes polymorphism on individual differences in propofol pharmacokinetics among Polish patients
        ]
    }
}


@dataclass
class PatientData:
    """
    Patient data structure containing only evidence-based parameters
    All fields map directly to published literature effects
    """
    # Demographics (affect MAC and dosing per literature)
    age: int
    weight_kg: float
    height_cm: float
    gender: str  # 'M' or 'F'

    # Clinical factors with proven impact
    asa_class: int  # 1-5, impacts dose per studies
    cardiovascular_disease: bool  # Affects propofol dose (PMID:28248699)
    heart_failure: bool  # Specific CV risk
    reactive_airway: bool  # Contraindicates desflurane (PMID:7818105)
    copd: bool  # Airway consideration
    diabetes: bool  # Diabetes mellitus - affects ASA and dosing
    hypertension: bool  # Hypertension - affects ASA classification
    smoking_status: str  # 'never', 'former', 'current' - affects ASA and anesthesia
    alcohol_use: str  # 'none', 'social', 'heavy' - affects ASA and metabolism

    # Pharmacokinetic genetic markers (affect metabolism/clearance)
    ryr1_variant: str  # 'Normal' or 'Variant' - MH risk
    cyp2b6: str  # 'PM', 'IM', 'NM', 'RM' - propofol/ketamine metabolism
    ugt1a9: str  # 'decreased', 'normal', 'increased' - propofol glucuronidation
    cyp3a4: str  # 'PM', 'IM', 'NM', 'RM' - ketamine metabolism
    cyp2c9: str  # 'PM', 'IM', 'NM', 'RM' - minor propofol/ketamine metabolism

    # Pharmacodynamic genetic markers (affect sensitivity/response curves)
    gabra1: str  # GABA-A receptor sensitivity (propofol/etomidate)
    comt: str    # Stress response and anesthetic requirement
    oprm1: str   # Opioid receptor sensitivity (ketamine NMDA effects)
    cacna1c: str  # Calcium channel sensitivity (cardiovascular response)

    # Procedural requirements
    procedure_duration_min: int  # Required for planning
    neuromonitoring: bool  # Affects volatile MAC limits (0.5 MAC max)

    def validate(self) -> List[str]:
        """Validate patient data completeness and ranges"""
        errors = []

        # Age validation
        if not 18 <= self.age <= 95:
            errors.append(f"Age {self.age} out of valid range (18-95 years)")

        # Weight validation
        if not 30 <= self.weight_kg <= 220:
            errors.append(
                f"Weight {self.weight_kg}kg out of valid range (30-220 kg)")

        # Height validation
        if not 120 <= self.height_cm <= 220:
            errors.append(
                f"Height {self.height_cm}cm out of valid range (120-220 cm)")

        # ASA validation
        if self.asa_class not in [1, 2, 3, 4, 5]:
            errors.append(f"ASA class {self.asa_class} invalid")

        # PK genetic variant validation
        valid_cyp2b6 = ['PM', 'IM', 'NM', 'RM']
        if self.cyp2b6 not in valid_cyp2b6:
            errors.append(f"CYP2B6 status {self.cyp2b6} not in {valid_cyp2b6}")

        valid_ugt1a9 = ['decreased', 'normal', 'increased']
        if self.ugt1a9 not in valid_ugt1a9:
            errors.append(f"UGT1A9 status {self.ugt1a9} not in {valid_ugt1a9}")

        valid_cyp3a4 = ['PM', 'IM', 'NM', 'RM']
        if self.cyp3a4 not in valid_cyp3a4:
            errors.append(f"CYP3A4 status {self.cyp3a4} not in {valid_cyp3a4}")

        valid_cyp2c9 = ['PM', 'IM', 'NM', 'RM']
        if self.cyp2c9 not in valid_cyp2c9:
            errors.append(f"CYP2C9 status {self.cyp2c9} not in {valid_cyp2c9}")

        if self.ryr1_variant not in ['Normal', 'Variant']:
            errors.append("RYR1 status must be 'Normal' or 'Variant'")

        # Clinical parameter validation
        if self.smoking_status not in ['never', 'former', 'current']:
            errors.append(f"Smoking status {self.smoking_status} not valid")

        if self.alcohol_use not in ['none', 'social', 'heavy']:
            errors.append(f"Alcohol use {self.alcohol_use} not valid")

        # PD genetic variant validation (fixed GABRA1 variant names)
        valid_gabra1 = ['rs4263535:G/G', 'rs4263535:A/G', 'rs4263535:A/A']
        if self.gabra1 not in valid_gabra1:
            errors.append(
                f"GABRA1 variant {self.gabra1} not in {valid_gabra1}")

        valid_comt = ['Val158Met:Met/Met',
                      'Val158Met:Val/Met', 'Val158Met:Val/Val']
        if self.comt not in valid_comt:
            errors.append(f"COMT variant {self.comt} not in {valid_comt}")

        valid_oprm1 = ['A118G:G/G', 'A118G:A/G', 'A118G:A/A']
        if self.oprm1 not in valid_oprm1:
            errors.append(f"OPRM1 variant {self.oprm1} not in {valid_oprm1}")

        valid_cacna1c = ['rs1006737:A/A', 'rs1006737:A/G', 'rs1006737:G/G']
        if self.cacna1c not in valid_cacna1c:
            errors.append(
                f"CACNA1C variant {self.cacna1c} not in {valid_cacna1c}")

        return errors


def calculate_asa_class(age: int, weight_kg: float, height_cm: float,
                        cardiovascular_disease: bool, heart_failure: bool,
                        reactive_airway: bool, copd: bool, diabetes: bool,
                        hypertension: bool, smoking_status: str, alcohol_use: str) -> Tuple[int, str]:
    """
    Calculate ASA Physical Status Classification based on official ASA guidelines
    Reference: https://www.asahq.org/standards-and-practice-parameters/statement-on-asa-physical-status-classification-system
    """
    bmi = weight_kg / ((height_cm / 100) ** 2)

    # ASA IV: Severe systemic disease that is constant threat to life
    if heart_failure:
        return 4, "ASA IV: Heart failure (severe systemic disease - constant threat to life)"

    # ASA III: Severe systemic disease
    if (copd or
        (cardiovascular_disease and (age > 70 or diabetes)) or
        bmi >= 40 or  # Morbid obesity
            (diabetes and (cardiovascular_disease or bmi > 35))):
        reasons = []
        if copd:
            reasons.append("COPD")
        if cardiovascular_disease and age > 70:
            reasons.append("CVD + age >70")
        if cardiovascular_disease and diabetes:
            reasons.append("CVD + diabetes")
        if bmi >= 40:
            reasons.append(f"morbid obesity (BMI {bmi:.1f})")
        if diabetes and bmi > 35:
            reasons.append("diabetes + obesity")
        return 3, f"ASA III: Severe systemic disease ({', '.join(reasons)})"

    # ASA II: Mild systemic disease
    if (diabetes or hypertension or cardiovascular_disease or reactive_airway or
        30 <= bmi < 40 or  # Obesity
        smoking_status == 'current' or
        alcohol_use == 'heavy' or
            age > 80):
        reasons = []
        if diabetes:
            reasons.append("diabetes")
        if hypertension:
            reasons.append("hypertension")
        if cardiovascular_disease:
            reasons.append("cardiovascular disease")
        if reactive_airway:
            reasons.append("reactive airway")
        if 30 <= bmi < 40:
            reasons.append(f"obesity (BMI {bmi:.1f})")
        if smoking_status == 'current':
            reasons.append("current smoking")
        if alcohol_use == 'heavy':
            reasons.append("heavy alcohol use")
        if age > 80:
            reasons.append("advanced age")
        return 2, f"ASA II: Mild systemic disease ({', '.join(reasons)})"

    # ASA I: Normal healthy patient
    return 1, "ASA I: Normal healthy patient (no systemic disease)"


class RouteSelector:
    """
    Selects induction route based ONLY on evidence-based contraindications
    No arbitrary scoring - uses feasibility assessment
    """

    def __init__(self):
        self.contraindications = {
            'IV': [],  # No absolute contraindications for IV
            'Inhalation': []
        }
        self.factors = []

    def assess_route_feasibility(self, patient: PatientData) -> Dict:
        """
        Assess route feasibility based on evidence-based contraindications
        Returns feasibility status and contributing factors
        """
        result = {
            'IV': {'feasible': True, 'factors': [], 'evidence': []},
            'Inhalation': {'feasible': True, 'factors': [], 'evidence': []}
        }

        # 1. RYR1 Variant - Absolute contraindication for volatiles (PMID:31386658)
        if patient.ryr1_variant == 'Variant':
            result['Inhalation']['feasible'] = False
            result['Inhalation']['factors'].append({
                'factor': 'RYR1 Variant',
                'impact': 'Absolute contraindication',
                'evidence': 'PMID:31386658 - MH susceptibility'
            })
            result['IV']['factors'].append({
                'factor': 'RYR1 Variant',
                'impact': 'Mandates IV route',
                'evidence': 'MHAUS Guidelines 2023'
            })

        # 2. Cardiovascular considerations (preference, not contraindication)
        if patient.cardiovascular_disease or patient.heart_failure:
            result['IV']['factors'].append({
                'factor': 'Cardiovascular disease',
                'impact': 'Better hemodynamic control',
                'evidence': 'PMID:28248699 - IV titratable'
            })
            # Note: NOT a contraindication for inhalation
            result['Inhalation']['factors'].append({
                'factor': 'Cardiovascular disease',
                'impact': 'Requires careful titration',
                'evidence': 'Clinical consideration'
            })

        # 3. High ASA status (ASA 4-5) - Strong preference for IV
        if patient.asa_class >= 4:
            result['IV']['factors'].append({
                'factor': f'ASA {patient.asa_class}',
                'impact': 'Preferred for critical patients',
                'evidence': 'PMID:26378978 - ASA guidelines'
            })

        # 4. Age considerations for pediatric (if < 12)
        if patient.age < 12:
            result['Inhalation']['factors'].append({
                'factor': 'Pediatric patient',
                'impact': 'Often preferred in children',
                'evidence': 'PMID:30843482 - Pediatric practice'
            })

        return result

    def select_route(self, patient: PatientData) -> Dict:
        """
        Select optimal route based on feasibility assessment
        For adults (18-95 years)
        """
        feasibility = self.assess_route_feasibility(patient)

        # Check absolute contraindications first
        iv_feasible = feasibility['IV']['feasible']
        inh_feasible = feasibility['Inhalation']['feasible']

        if not inh_feasible:
            chosen_route = 'IV'
            reason = 'Inhalation contraindicated'
        elif not iv_feasible:
            chosen_route = 'Inhalation'
            reason = 'IV contraindicated'
        else:
            # Both feasible - use evidence-based selection criteria
            # Stronger nudges for high-risk patients
            if patient.age >= 18:
                # Strong preference for IV in high-risk patients
                if (patient.asa_class >= 3 or
                        patient.cardiovascular_disease or
                        patient.heart_failure):
                    chosen_route = 'IV'
                    if patient.asa_class >= 4:
                        reason = ('IV strongly preferred for ASA 4+ - '
                                  'critical patient requires precise control')
                    elif patient.heart_failure:
                        reason = ('IV strongly preferred for heart failure - '
                                  'titratable hemodynamic control essential')
                    elif patient.cardiovascular_disease:
                        reason = ('IV preferred for cardiovascular disease - '
                                  'better hemodynamic stability')
                    else:
                        reason = ('IV preferred for ASA 3 - '
                                  'better control for significant disease')
                else:
                    chosen_route = 'IV'
                    reason = 'Standard adult practice'
            else:
                chosen_route = 'Inhalation'
                reason = 'Pediatric preference'

        return {
            'chosen_route': chosen_route,
            'reason': reason,
            'feasibility': feasibility,
            'evidence_base': self._get_route_evidence(chosen_route),
            'risk_factors': self._get_risk_factors(patient)
        }

    def _get_risk_factors(self, patient: PatientData) -> List[str]:
        """Identify risk factors affecting route selection"""
        factors = []
        if patient.asa_class >= 4:
            factors.append(f'ASA {patient.asa_class} - Critical illness')
        elif patient.asa_class == 3:
            factors.append('ASA 3 - Severe systemic disease')

        if patient.heart_failure:
            factors.append('Heart failure - Requires precise control')
        elif patient.cardiovascular_disease:
            factors.append('Cardiovascular disease - Hemodynamic risk')

        if patient.ryr1_variant == 'Variant':
            factors.append('RYR1 variant - MH susceptibility')

        return factors

    def _get_route_evidence(self, route: str) -> List[str]:
        """Return evidence supporting route choice"""
        if route == 'IV':
            return [
                'PMID:28248699 - Titratable hemodynamic control',
                'PMID:26378978 - ASA practice guidelines',
                'Standard of care for adult induction'
            ]
        else:
            return [
                'PMID:30843482 - Pediatric anesthesia guidelines',
                'PMID:7818105 - Sevoflurane smooth induction',
                'Avoids injection pain'
            ]


class AgentSelector:
    """
    Selects anesthetic agent based on evidence-based criteria
    No arbitrary preferences - uses published contraindications and indications
    """

    def __init__(self):
        self.iv_agents = ['Propofol', 'Etomidate', 'Ketamine']
        self.volatile_agents = ['Sevoflurane', 'Desflurane', 'Isoflurane']

    def assess_iv_agents(self, patient: PatientData) -> Dict:
        """
        Assess IV agents based on evidence-based indications/contraindications
        """
        assessment = {}

        # PROPOFOL Assessment
        propofol = {
            'feasible': True,
            'advantages': [],
            'disadvantages': [],
            'evidence': []
        }

        # Cardiovascular effects
        if patient.cardiovascular_disease or patient.asa_class >= 3:
            propofol['disadvantages'].append({
                'factor': 'Hypotension risk',
                'magnitude': (
                    '≈20–35% severe (MAP≤55) in older adults; '
                    '≈28% SBP<90 for >5 min in procedural sedation; '
                    'risk amplified with ASA≥III and higher propofol dose'
                ),
                'evidence': [
                    'PMID:35489305',  # 320k pts ≥65y; severe MAP≤55 pre-incision 22.6%; dose association
                    'PMID:34916051',  # BJA meta-analysis; ~28% SBP<90 for >5 min in colonoscopy sedation
                    # 25k+ cases; 15.7% SBP<90 after propofol induction (ASA I–III)
                    'PMID:8214693',
                    'PMID:34859868',  # Systematic review; ASA III–V and propofol induction as risk factors
                ],
                'definition_note': 'Incidence depends on threshold (SBP<90 vs MAP≤65/55), population, and dosing'
            })

        # Standard first-line agent
        propofol['advantages'].append({
            'factor': 'Reduced PONV and smoother recovery vs volatiles',
            'magnitude': 'Meta-analysis shows lower early/late PONV with propofol TIVA',
            'evidence': [
                'PMID:25296857 – systematic review/meta-analysis on propofol vs inhalation agents and PONV reduction',
                # optionally add a second reference if you want emergence agitation specifically
            ]
        })

        assessment['Propofol'] = propofol

        # ETOMIDATE Assessment
        etomidate = {
            'feasible': True,
            'advantages': [],
            'disadvantages': [],
            'evidence': []
        }

        # Stricter contraindications for cardiovascular disease
        if patient.cardiovascular_disease and patient.asa_class >= 4:
            etomidate['feasible'] = False
            etomidate['contraindication'] = (
                'Adrenal suppression risk in critically ill '
                'cardiovascular patients'
            )
            etomidate['evidence'] = [
                ('PMID:22441015 – meta-analysis: adrenal suppression '
                 'increases mortality in critically ill'),
                ('PMID:29368625 – review: avoid etomidate in sepsis/shock '
                 'due to adrenal effects')
            ]
        elif patient.cardiovascular_disease and patient.diabetes:
            etomidate['disadvantages'].append({
                'factor': ('Adrenal suppression in diabetic '
                           'cardiovascular patients'),
                'magnitude': (
                    'Increased risk of perioperative stress response '
                    'complications'
                ),
                'evidence': [
                    'PMID:22441015 – adrenal suppression effects',
                    ('PMID:23426219 – clinical significance in '
                     'stressed patients')
                ]
            })

        # Hemodynamic stability (only if still feasible)
        if (etomidate['feasible'] and
                (patient.cardiovascular_disease or patient.asa_class >= 3)):
            etomidate['advantages'].append({
                'factor': 'Hemodynamic stability',
                'magnitude': (
                    'Significantly less MAP/HR drop vs propofol '
                    '(e.g., <10% MAP decrease)'
                ),
                'evidence': [
                    ('PMID:31761720 – RCT: cardiac patients, less '
                     'hypotension vs propofol'),
                    ('PMID:32654187 – meta-analysis: stable hemodynamics '
                     'with etomidate induction')
                ]
            })

        # Adrenal suppression
        etomidate['disadvantages'].append({
            'factor': 'Adrenal suppression',
            'magnitude': 'Inhibits 11β-hydroxylase; transient cortisol/aldosterone synthesis reduction (~6–24h)',
            'evidence': [
                'PMID:22441015 – meta-analysis: measurable adrenal suppression post-etomidate',
                'PMID:17060330 – RCT: suppression up to 24h',
                'PMID:23426219 – review: effect and clinical context'
            ]
        })

        assessment['Etomidate'] = etomidate

        # KETAMINE Assessment
        ketamine = {
            'feasible': True,
            'advantages': [],
            'disadvantages': [],
            'evidence': []
        }

        # Stricter contraindications for hypertensive patients
        if patient.hypertension and patient.cardiovascular_disease:
            ketamine['feasible'] = False
            ketamine['contraindication'] = (
                'Hypertension with cardiovascular disease - '
                'sympathomimetic effects increase cardiac risk'
            )
            ketamine['evidence'] = [
                ('PMID:26867833 – review: ketamine raises HR/BP; '
                 'contraindicated in uncontrolled HTN'),
                ('PMID:23250431 – cardiovascular profile; avoid in CAD '
                 'with HTN')
            ]
        elif patient.hypertension and patient.asa_class >= 4:
            ketamine['disadvantages'].append({
                'factor': 'Hypertension in critically ill patients',
                'magnitude': (
                    'Sympathomimetic effects may exacerbate hypertensive '
                    'crisis in unstable patients'
                ),
                'evidence': [
                    ('PMID:26867833 – review: ketamine contraindicated '
                     'in severe uncontrolled HTN'),
                    'PMID:23250431 – cardiovascular monitoring required'
                ]
            })

        # Bronchodilation in reactive airway
        if patient.reactive_airway or patient.copd:
            ketamine['advantages'].append({
                'factor': 'Bronchodilation',
                'magnitude': 'Improves airway resistance; beneficial in asthma/COPD exacerbations',
                'evidence': [
                    'PMID:29487156 – review: ketamine reduces airway resistance in status asthmaticus',
                    'PMID:20656763 – case series: improved ventilation in refractory asthma'
                ]
            })

        # Sympathomimetic effects
        if not patient.cardiovascular_disease:
            ketamine['advantages'].append({
                'factor': 'Maintained or increased BP',
                'magnitude': 'Sympathomimetic effect via catecholamine release/reuptake inhibition; supports BP/HR in normovolemic patients',
                'evidence': [
                    'PMID:26867833 – review: ketamine maintains BP/CO via sympathomimetic effects',
                    'PMID:23250431 – cardiovascular profile in trauma/induction',
                ]
            })
        else:
            ketamine['disadvantages'].append({
                'factor': 'Increased myocardial O₂ demand',
                'magnitude': 'Sympathomimetic effects can raise HR/BP; caution in CAD or ischemic heart disease',
                'evidence': [
                    'PMID:26867833 – review: ketamine raises HR/BP; risk of ischemia in CAD',
                    'PMID:23250431 – cardiovascular profile; CAD caution'
                ]
            })

        assessment['Ketamine'] = ketamine

        return assessment

    def assess_volatile_agents(self, patient: PatientData) -> Dict:
        """
        Assess volatile agents based on evidence
        """
        assessment = {}

        # Check RYR1 first - absolute contraindication
        if patient.ryr1_variant == 'Variant':
            for agent in self.volatile_agents:
                assessment[agent] = {
                    'feasible': False,
                    'contraindication': 'RYR1 pathogenic variant – absolute MH trigger with volatiles',
                    'evidence': [
                        'PMID:31386658 – review: RYR1 variants predispose to MH with volatile agents',
                        'MHAUS Guidelines 2023 – volatiles are absolute MH triggers'
                    ]
                }
            return assessment

        # SEVOFLURANE Assessment
        sevoflurane = {
            'feasible': True,
            'advantages': [],
            'disadvantages': [],
            'evidence': []
        }

        sevoflurane['advantages'].append({
            'factor': 'Low airway irritation',
            'magnitude': 'Non-pungent; <5% incidence of cough/laryngospasm during inhalation induction',
            'evidence': [
                'PMID:8250714 – study: low airway reflex incidence with sevoflurane',
                'PMID:8659733 – smooth inhalation induction, minimal airway reactivity'
            ]
        })

        assessment['Sevoflurane'] = sevoflurane

        # DESFLURANE Assessment
        desflurane = {
            'feasible': True,
            'advantages': [],
            'disadvantages': [],
            'evidence': []
        }

        # Airway irritation contraindication (PMID:7818105)
        if patient.reactive_airway or patient.copd:
            desflurane['feasible'] = False
            desflurane['contraindication'] = 'High airway irritability; risk of cough/laryngospasm in reactive airway/COPD patients'
            desflurane['evidence'] = [
                'PMID:7818105 – study: ~34% incidence cough/laryngospasm during inhalation induction',
                'PMID:8659733 – higher airway reactivity vs sevoflurane'
            ]

        else:
            desflurane['advantages'].append({
                'factor': 'Rapid emergence',
                'magnitude': 'Very low blood:gas partition coefficient (~0.42); faster wake-up vs isoflurane/sevoflurane',
                'evidence': [
                    'PMID:1952180 – early study: rapid recovery profile',
                    'PMID:7631926 – faster emergence and psychomotor recovery vs isoflurane'
                ]
            })

        assessment['Desflurane'] = desflurane

        # ISOFLURANE Assessment
        isoflurane = {
            'feasible': True,
            'advantages': [],
            'disadvantages': [],
            'evidence': []
        }

        isoflurane['disadvantages'].append({
            'factor': 'Pungent odor and airway irritation',
            'magnitude': 'Higher incidence of cough/breath-holding vs sevoflurane',
            'evidence': [
                'PMID:7818105 – higher airway reactivity vs sevoflurane'
            ]
        })

        assessment['Isoflurane'] = isoflurane

        return assessment

    def select_agent(self, patient: PatientData, route: str) -> Dict:
        """
        Select optimal agent based on assessment
        """
        if route == 'IV':
            assessments = self.assess_iv_agents(patient)
        else:
            assessments = self.assess_volatile_agents(patient)

        # Filter feasible agents
        feasible = {name: data for name, data in assessments.items()
                    if data.get('feasible', False)}

        if not feasible:
            return {
                'chosen_agent': None,
                'reason': 'No feasible agents',
                'assessments': assessments
            }

        # Score based on advantage/disadvantage balance
        scores = {}
        for agent, data in feasible.items():
            advantage_score = len(data.get('advantages', []))
            disadvantage_score = len(data.get('disadvantages', []))
            scores[agent] = advantage_score - disadvantage_score

        # Select highest scoring agent
        if scores:
            chosen_agent = max(scores.keys(), key=lambda x: scores[x])
        else:
            chosen_agent = list(feasible.keys())[0] if feasible else None

        return {
            'chosen_agent': chosen_agent,
            'score': scores.get(chosen_agent, 0) if chosen_agent else 0,
            'advantages': feasible[chosen_agent]['advantages'] if chosen_agent else [],
            'disadvantages': feasible[chosen_agent]['disadvantages'] if chosen_agent else [],
            'all_assessments': assessments
        }


class DoseCalculator:
    """
    Calculate doses using only evidence-based adjustments
    All modifications traceable to published literature
    """

    def __init__(self):
        # Base doses from Miller's Anesthesia 9th Ed
        self.base_iv_doses = {
            'Propofol': 2.0,     # mg/kg (PMID:32304223)
            'Etomidate': 0.3,    # mg/kg (PMID:31761720)
            'Ketamine': 2.0      # mg/kg (PMID:29487156)
        }

        # MAC values at age 40
        self.base_mac_values = {
            'Sevoflurane': 2.0,  # % (PMID:8250714)
            'Desflurane': 6.0,   # % (PMID:1952180)
            'Isoflurane': 1.2    # % (PMID:6859426)
        }

    def calculate_age_adjusted_mac(self, base_mac: float, age: int) -> Dict:
        """
        Age adjustment for MAC using Mapleson equation (base-10 model).
        Reference: Mapleson WW. Effect of age on MAC in humans: a meta-analysis.
        PMID:8777094. Also summarized in StatPearls and Nickalls' iso-MAC charts.
        """
        if age <= 40:
            adjustment_factor = 1.0
        else:
            years_over_40 = age - 40
            # Mapleson uses log10 model: MAC_age = MAC_40 * 10^(b * Δage), b = -0.00269
            adjustment_factor = 10 ** (-0.00269 * years_over_40)

        adjusted_mac = base_mac * adjustment_factor
        return {
            "base_mac": base_mac,
            "adjusted_mac": adjusted_mac,
            "age": age,
            "adjustment_factor": adjustment_factor,
            "evidence": "Mapleson 1996 meta-analysis; b=-0.00269 (base-10). PMID:8777094"
        }

    def calculate_pk_adjustment(self, agent: str, patient: PatientData) -> dict:
        """
        Pharmacokinetic dose-adjustment multipliers from validated genetic effects.
        Combines pathway-specific clearances; dose ~ 1 / total_clearance.
        """
        adj = 1.0
        factors = []

        if agent == "Propofol":
            # Pathway weights (fraction of total CL) – updated per new research
            w_ugt1a9 = 0.40   # Updated dominant glucuronidation fraction
            w_cyp_ox = 1 - w_ugt1a9  # Combined oxidative: CYP2B6 ± CYP2C9

            # UGT1A9 effect
            ugt1a9_lookup = {
                "decreased": 0.85,   # provisional, avoid aggressive 0.75 without allele context
                "normal":    1.00,
                "increased": 1.15    # provisional
            }
            ugt1a9_fx = ugt1a9_lookup.get(
                getattr(patient, "ugt1a9", "normal"), 1.0)

            # CYP2B6 effect (oxidation driver within CYP bin)
            cyp2b6_lookup = {
                "PM": 0.80,  # provisional; in vitro shows large variability; keep conservative
                "IM": 0.90,
                "NM": 1.00,
                "RM": 1.10
            }
            cyp2b6_fx = cyp2b6_lookup.get(
                getattr(patient, "cyp2b6", "NM"), 1.0)

            # Combine pathway clearances (fractional)
            total_cl = (w_ugt1a9 * ugt1a9_fx) + (w_cyp_ox * cyp2b6_fx)
            adj = 1.0 / total_cl

            factors += [
                {
                    "gene": "UGT1A9",
                    "phenotype": getattr(patient, "ugt1a9", "normal"),
                    "pathway_weight": w_ugt1a9,
                    "clearance_multiplier": ugt1a9_fx,
                    "evidence": [
                        "UGT1A9 is primary propofol pathway (dominant glucuronidation)."
                    ],
                    "refs": ["PMCID:PMC5994321", "PMCID:PMC8918542", "BJA 2025 summary"]
                },
                {
                    "gene": "CYP2B6",
                    "phenotype": getattr(patient, "cyp2b6", "NM"),
                    "pathway_weight": w_cyp_ox,
                    "clearance_multiplier": cyp2b6_fx,
                    "evidence": [
                        "CYP2B6 is principal P450 for propofol hydroxylation (in vitro)."
                    ],
                    "refs": ["PMCID:PMC2015030", "PMID:11135730"]
                }
            ]

        elif agent == "Ketamine":
            # Pathway weights for N-demethylation (updated with new research)
            w_cyp3a4 = 0.75   # Updated principal pathway
            w_cyp2b6 = 0.25   # Updated contributory pathway

            # Map genotype/phenotype to cautious multipliers
            cyp3a4_lookup = {
                # Better: derive from *22/*1G carrier status if available
                "PM": 0.80,  # placeholder for *22 carriers
                "IM": 0.90,
                "NM": 1.00,
                "RM": 1.10  # placeholder for *1G or induction state
            }
            ph3a4 = getattr(patient, "cyp3a4", "NM")
            cyp3a4_fx = cyp3a4_lookup.get(ph3a4, 1.0)

            cyp2b6_lookup = {"PM": 0.85, "IM": 0.93, "NM": 1.00, "RM": 1.10}
            cyp2b6_fx = cyp2b6_lookup.get(
                getattr(patient, "cyp2b6", "NM"), 1.0)

            total_cl = (w_cyp3a4 * cyp3a4_fx) + (w_cyp2b6 * cyp2b6_fx)
            adj = 1.0 / total_cl

            factors += [
                {
                    "gene": "CYP3A4",
                    "phenotype": ph3a4,
                    "pathway_weight": w_cyp3a4,
                    "clearance_multiplier": cyp3a4_fx,
                    "evidence": ["CYP3A4 is principal for ketamine N-demethylation."],
                    "refs": ["PMID:12065445", "PMCID:PMC6197107"]
                },
                {
                    "gene": "CYP2B6",
                    "phenotype": getattr(patient, "cyp2b6", "NM"),
                    "pathway_weight": w_cyp2b6,
                    "clearance_multiplier": cyp2b6_fx,
                    "evidence": ["CYP2B6 contributes to ketamine metabolism."],
                    "refs": ["PMCID:PMC6197107"]
                }
            ]

        return {
            "adjustment_factor": adj,
            "genetic_factors": factors
        }

    def calculate_clinical_adjustments(self, agent: str, patient: PatientData) -> dict:
        """
        Evidence-grounded clinical (non-genetic) dose multipliers.
        """

        adj = 1.0
        factors = []

        # AGE: apply for IV hypnotics (propofol/etomidate/ketamine) with strongest data for propofol
        if agent in ("Propofol", "Etomidate", "Ketamine"):
            if patient.age >= 75:
                # ~35% reduction vs younger adults (LOC studies & geriatric guidance)
                age_factor = 0.65
                factors.append({
                    "factor": "Age ≥ 75",
                    "adjustment": age_factor,
                    "evidence": [
                        "Propofol requirement falls 25–40% with age; larger ≥75.",
                        "Geriatric ranges commonly ≤1–1.5 mg/kg."
                    ],
                    "refs": ["PMID:35418861", "PMCID:PMC8373744", "PMCID:PMC5864105"]
                })
                adj *= age_factor
            elif patient.age >= 65:
                age_factor = 0.80   # ~20% reduction typical 65–74
                factors.append({
                    "factor": "Age 65–74",
                    "adjustment": age_factor,
                    "evidence": [
                        "Elderly require lower propofol doses; reduce vs adults <65."
                    ],
                    "refs": ["PMID:35418861", "PMCID:PMC5864105"]
                })
                adj *= age_factor

        # CARDIOVASCULAR DISEASE/HEART FAILURE: propofol hypotension risk → reduce/titrate
        if agent == "Propofol" and (getattr(patient, "cardiovascular_disease", False) or getattr(patient, "heart_failure", False)):
            cv_factor = 0.80  # conservative 20% reduction; prefer slow titration/TCI if available
            factors.append({
                "factor": "Cardiovascular disease / heart failure",
                "adjustment": cv_factor,
                "evidence": [
                    "Propofol causes vasodilation & hypotension; higher risk in cardiac disease.",
                    "Consider etomidate in hemodynamically unstable CAD."
                ],
                "refs": ["PMID:7914708", "NBK430884", "PMCID:PMC7896684"]
            })
            adj *= cv_factor

        # ASA CLASS: reduce for ASA 3–4 (frailty/comorbidity)
        if getattr(patient, "asa_class", None) is not None and patient.asa_class >= 3:
            # Stepwise: ASA3 ~0.85; ASA4+ ~0.75
            asa_factor = 0.75 if patient.asa_class >= 4 else 0.85
            factors.append({
                "factor": f"ASA {patient.asa_class} (Physical Status Classification)",
                "adjustment": asa_factor,
                "evidence": [
                    (f"ASA {patient.asa_class} patients require reduced induction "
                     f"doses due to "
                     f"{'critical illness/organ dysfunction' if patient.asa_class >= 4 else 'severe systemic disease'}."),
                    ("Higher ASA classes associated with increased drug "
                     "sensitivity and hemodynamic instability requiring "
                     "dose reduction."),
                    (f"Applied {int((1-asa_factor)*100)}% dose reduction "
                     f"for ASA {patient.asa_class}.")
                ],
                "refs": ["PMCID:PMC6267518",
                         "ASA Physical Status Classification System"],
                "audit_note": (
                    f"ASA {patient.asa_class} multiplicative dose reduction: "
                    f"{asa_factor} (baseline × {asa_factor} = "
                    f"{int(asa_factor*100)}% of standard dose)"
                )
            })
            adj *= asa_factor

        return {
            "adjustment_factor": adj,
            "clinical_factors": factors
        }

    def calculate_dose(self, agent: str, patient: PatientData, route: str) -> dict:
        """
        Calculate final dose with evidence-based adjustments.
        """

        # Helper functions for body weight calculations
        def boer_lbw(kg, cm, sex):
            # Boer (lean body weight) — robust for anesthetic induction scaling
            if str(sex).lower().startswith("m"):
                return 0.407*kg + 0.267*cm - 19.2
            else:
                return 0.252*kg + 0.473*cm - 48.3

        def devine_ibw(cm, sex):
            # Devine IBW (kg)
            inches_over_5ft = max(0.0, (cm/2.54) - 60.0)
            base = 50.0 if str(sex).lower().startswith("m") else 45.5
            return base + 2.3*inches_over_5ft

        TBW = float(patient.weight_kg)
        Ht = float(patient.height_cm)
        BMI = TBW / (Ht/100.0)**2
        SEX = getattr(patient, "gender", "M")

        LBW = boer_lbw(TBW, Ht, SEX)
        IBW = devine_ibw(Ht, SEX)

        # Choose dosing scalar per agent/obesity evidence
        if route == "IV":
            # Scalars & max ceilings (mg/kg) anchored to labels/guidelines
            if agent == "Propofol":
                # Induction should scale to **LBW** in obesity to avoid overshoot
                dosing_weight = LBW if BMI >= 30 else TBW
                label_ceiling_mg_per_kg = 2.5  # adult induction upper end
                ceiling_source = "Propofol label 2–2.5 mg/kg adults <65."  # FDA/PI
                ceiling_ref = "accessdata.fda.gov (DIPRIVAN PI)"

            elif agent == "Etomidate":
                # Etomidate: ABW/TBW acceptable; ≥40 BMI consider Adj/ABW.
                dosing_weight = (TBW if BMI < 40 else max(IBW, LBW))
                label_ceiling_mg_per_kg = 0.6  # label range 0.2–0.6 mg/kg
                ceiling_source = "Amidate label 0.2–0.6 mg/kg; adrenal suppression ~0.3 mg/kg noted."
                ceiling_ref = "FDA Amidate label"

            elif agent == "Ketamine":
                # Ketamine: in obesity prefer **IBW/AdjBW** for weight-based bolus.
                dosing_weight = (IBW if BMI >= 30 else TBW)
                label_ceiling_mg_per_kg = 2.0
                ceiling_source = "Adult induction 1–2 mg/kg; label broader but clinical practice ceiling 2 mg/kg."
                ceiling_ref = "FDA Ketalar label; StatPearls"

            else:
                raise ValueError(f"Unsupported IV agent: {agent}")

            base_per_kg = self.base_iv_doses[agent]  # must be mg/kg
            base_dose_mg = base_per_kg * dosing_weight

            # Apply PK + clinical adjustments (both return {'adjustment_factor': x, ...})
            pk_adj = self.calculate_pk_adjustment(agent, patient)
            clin_adj = self.calculate_clinical_adjustments(agent, patient)
            total_adj = pk_adj["adjustment_factor"] * \
                clin_adj["adjustment_factor"]

            # Provisional dose before ceiling
            adjusted_mg = base_dose_mg * total_adj

            # Safety ceiling (mg) with dynamic adjustments for vulnerable populations
            base_ceiling_mg = label_ceiling_mg_per_kg * dosing_weight

            # Apply dynamic dosing ceilings for vulnerable populations
            ceiling_reduction_factor = 1.0
            ceiling_adjustments = []

            # Age-based ceiling reductions
            if patient.age >= 85:
                ceiling_reduction_factor *= 0.75  # 25% reduction for very elderly
                ceiling_adjustments.append("25% reduction for age ≥85")
            elif patient.age >= 75:
                ceiling_reduction_factor *= 0.85  # 15% reduction for elderly
                ceiling_adjustments.append("15% reduction for age ≥75")

            # Comorbidity-based ceiling reductions
            if patient.heart_failure:
                ceiling_reduction_factor *= 0.8  # 20% reduction for heart failure
                ceiling_adjustments.append("20% reduction for heart failure")
            elif patient.cardiovascular_disease and patient.asa_class >= 4:
                ceiling_reduction_factor *= 0.85  # 15% reduction for critical CVD
                ceiling_adjustments.append("15% reduction for critical CVD")

            # ASA-based ceiling reductions
            if patient.asa_class >= 5:
                ceiling_reduction_factor *= 0.7  # 30% reduction for ASA 5
                ceiling_adjustments.append("30% reduction for ASA 5")
            elif patient.asa_class == 4:
                ceiling_reduction_factor *= 0.85  # 15% reduction for ASA 4
                ceiling_adjustments.append("15% reduction for ASA 4")

            # Calculate final ceiling with reductions
            dynamic_ceiling_mg = base_ceiling_mg * ceiling_reduction_factor
            final_mg = min(adjusted_mg, dynamic_ceiling_mg)

            # Prepare ceiling note
            if ceiling_adjustments:
                dynamic_ceiling_note = (
                    f"{ceiling_source} Dynamic reductions: "
                    f"{', '.join(ceiling_adjustments)}"
                )
            else:
                dynamic_ceiling_note = ceiling_source

            return {
                "agent": agent,
                "route": "IV",
                "bmi": round(BMI, 1),
                "weight_scalar_used": (
                    "LBW" if dosing_weight == LBW else (
                        "IBW" if dosing_weight == IBW else "TBW")
                ),
                "dosing_weight_kg": round(dosing_weight, 1),
                "base_dose_per_kg": base_per_kg,
                "base_dose_mg": round(base_dose_mg, 1),
                "pk_adjustment": pk_adj,
                "clinical_adjustment": clin_adj,
                "total_adjustment": round(total_adj, 3),
                "final_dose_mg": round(final_mg, 1),
                "dose_mg_per_kg_on_scalar": round(final_mg / dosing_weight, 3),
                "units": "mg",
                "safety_ceiling_mg": round(dynamic_ceiling_mg, 1),
                "ceiling_note": dynamic_ceiling_note,
                "ceiling_adjustments": ceiling_adjustments,
                "evidence": [
                    # Provenance strings for UI/tooltips
                    ("Scalar based on obesity dosing literature"),
                    (f"Ceiling: {label_ceiling_mg_per_kg} mg/kg "
                     f"({ceiling_ref})"),
                ],
            }

        # Inhalational (volatile) path — keep Mapleson age correction
        else:
            base_mac = self.base_mac_values[agent]  # MAC40 %
            mac_adj = self.calculate_age_adjusted_mac(base_mac, patient.age)

            # Apply neuromonitoring MAC cap if required
            final_target = mac_adj["adjusted_mac"]
            cap_note = None

            if hasattr(patient, 'neuromonitoring') and patient.neuromonitoring:
                # Cap target MAC to 0.5 × age-adjusted MAC for neuromonitoring
                capped_target = mac_adj["adjusted_mac"] * 0.5
                final_target = capped_target
                cap_note = "0.5 MAC due to neuromonitoring"

            evidence_list = [
                "Age-MAC per Mapleson (base-10) / Nickalls charts.",
                mac_adj["evidence"],
            ]

            if cap_note:
                evidence_list.append(
                    f"Target capped to {cap_note} per clinical practice."
                )

            return {
                "agent": agent,
                "route": "Inhalation",
                "base_mac_percent_at_40": base_mac,
                "age_adjusted_mac_percent": mac_adj["adjusted_mac"],
                "adjustment_factor": mac_adj["adjustment_factor"],
                "final_target": final_target,
                "units": "% (MAC)",
                "cap": cap_note,
                "evidence": evidence_list,
            }


class EmaxModel:
    """
    Emax model for dose-response prediction with PD genetic integration
    Based on published EC50 values and Hill coefficients
    Incorporates pharmacodynamic genetics affecting sensitivity/response curves
    """

    def apply_pd_genetics(self, agent: str, patient, ec50_hypnosis: float, ec50_adverse: float):
        """
        Apply pharmacodynamic genetic effects to EC50 values (hypnosis, adverse).
        """
        mod_hyp = float(ec50_hypnosis)
        mod_adv = float(ec50_adverse)
        notes = []

        a = agent.lower()

        def apply_variant(gene_name, phenotype):
            nonlocal mod_hyp, mod_adv
            g = PD_GENETIC_EFFECTS.get(gene_name)
            if not g:
                return
            v = g.get("variants", {}).get(phenotype)
            if not v:
                return
            h_mult = float(v.get("ec50_adjustment", 1.0))
            ad_mult = h_mult  # Use same multiplier for both
            mod_hyp *= h_mult
            mod_adv *= ad_mult
            notes.append(f"{gene_name.upper()} {phenotype}: "
                         f"H-EC50×{h_mult:.2f}, A-EC50×{ad_mult:.2f}")

        # Evidence-backed adjustments
        if a == "propofol":
            # GABA-A receptor subunits: human association with propofol sedation and BP drop
            if hasattr(patient, "gabra1") and patient.gabra1:
                apply_variant("gabra1", patient.gabra1)

        return mod_hyp, mod_adv, notes

    def calculate_response_probabilities(self, dose_mg: float, weight_kg: float,
                                         agent: str, patient) -> dict:
        """
        Emax-based probabilities for hypnosis and adverse events (bolus context).
        """

        dose_mg_per_kg = dose_mg / max(float(weight_kg), 1e-6)

        # Evidence-anchored base EC50/Hill (bolus induction context)
        a = agent.lower()
        if a == "propofol":
            base_ec50_hypnosis = 1.8
            base_ec50_adverse = 2.3
            hill = 2.5
            evidence_blurb = (
                "Propofol ED50~1.6–2.0 & ED95~2.1–2.6 mg/kg (bolus); Ce50 LOC ≈2–2.3 μg/mL."
            )
            evidence_refs = ["PMCID:PMC11101821", "PMID:8110547",
                             "PMCID:PMC6343297", "PMCID:PMC1343509"]

        elif a == "ketamine":
            base_ec50_hypnosis = 1.0
            base_ec50_adverse = 2.8
            hill = 2.0
            evidence_blurb = "Adult IV induction typically 1–2 mg/kg; adverse rises at higher doses."
            evidence_refs = ["Heliyon 2024 dose–response LMA co-induction context",
                             "Ketalar/clinical practice summaries"]

        elif a == "etomidate":
            base_ec50_hypnosis = 0.25
            base_ec50_adverse = 0.40
            hill = 3.0
            evidence_blurb = "Induction 0.2–0.3 mg/kg; hypnosis ≳200 ng/mL; favorable hemodynamics."
            evidence_refs = ["NBK535364",
                             "PMCID:PMC3108152", "PMCID:PMC8505283"]

        else:
            # Generic fallback
            base_ec50_hypnosis = 1.0
            base_ec50_adverse = 2.0
            hill = 2.0
            evidence_blurb = "Generic fallback (no agent-specific PD)."
            evidence_refs = []

        # Apply PD genetics
        if patient:
            adj_ec50_h, adj_ec50_a, pd_notes = self.apply_pd_genetics(
                agent, patient, base_ec50_hypnosis, base_ec50_adverse
            )
        else:
            adj_ec50_h, adj_ec50_a, pd_notes = base_ec50_hypnosis, base_ec50_adverse, []

        # Apply safety-based E-max threshold adjustments for vulnerable populations
        adverse_threshold_adjustments = []
        adverse_threshold_factor = 1.0

        # Age-based adverse event threshold lowering
        if hasattr(patient, 'age'):
            if patient.age >= 85:
                # 25% lower threshold (more sensitive)
                adverse_threshold_factor *= 0.75
                adverse_threshold_adjustments.append(
                    "25% lower threshold for age ≥85")
            elif patient.age >= 75:
                adverse_threshold_factor *= 0.85  # 15% lower threshold
                adverse_threshold_adjustments.append(
                    "15% lower threshold for age ≥75")

        # Comorbidity-based adverse event threshold lowering
        if hasattr(patient, 'heart_failure') and patient.heart_failure:
            adverse_threshold_factor *= 0.8  # 20% lower threshold
            adverse_threshold_adjustments.append(
                "20% lower threshold for heart failure")
        elif (hasattr(patient, 'cardiovascular_disease') and
              hasattr(patient, 'asa_class') and
              patient.cardiovascular_disease and patient.asa_class >= 4):
            adverse_threshold_factor *= 0.85  # 15% lower threshold
            adverse_threshold_adjustments.append(
                "15% lower threshold for critical CVD")

        # ASA-based adverse event threshold lowering
        if hasattr(patient, 'asa_class'):
            if patient.asa_class >= 5:
                adverse_threshold_factor *= 0.7  # 30% lower threshold
                adverse_threshold_adjustments.append(
                    "30% lower threshold for ASA 5")
            elif patient.asa_class == 4:
                adverse_threshold_factor *= 0.85  # 15% lower threshold
                adverse_threshold_adjustments.append(
                    "15% lower threshold for ASA 4")

        # Apply threshold adjustments to adverse event EC50
        adjusted_ec50_adverse_final = adj_ec50_a * adverse_threshold_factor

        # Add safety adjustment notes to PD notes
        if adverse_threshold_adjustments:
            safety_note = f"Safety thresholds: {', '.join(adverse_threshold_adjustments)}"
            pd_notes.append(safety_note)

        # Emax (Hill) calculations
        def hill_prob(d, ec50, n):
            # P = d^n / (ec50^n + d^n)
            dn = d ** n
            return dn / (ec50 ** n + dn)

        p_hypnosis = min(hill_prob(dose_mg_per_kg, adj_ec50_h, hill), 1.0)
        p_adverse = min(
            hill_prob(dose_mg_per_kg, adjusted_ec50_adverse_final, hill), 1.0)

        # Evidence string (transparent provenance)
        evidence = [
            evidence_blurb,
            "Emax/Hill form standard in anesthetic PK/PD; TCI review provides context."
        ]
        if pd_notes:
            evidence.append("PD genetics applied: " + "; ".join(pd_notes))

        return {
            "agent": agent,
            "dose_mg_per_kg": dose_mg_per_kg,
            "p_hypnosis": p_hypnosis,
            "p_adverse": p_adverse,
            "therapeutic_index": p_hypnosis / max(p_adverse, 1e-6),
            "base_ec50_hypnosis": base_ec50_hypnosis,
            "adjusted_ec50_hypnosis": adj_ec50_h,
            "base_ec50_adverse": base_ec50_adverse,
            "adjusted_ec50_adverse": adjusted_ec50_adverse_final,
            "safety_adjustments": adverse_threshold_adjustments,
            "hill": hill,
            "genetic_effects": pd_notes,
            "evidence": {
                "summary": evidence,
                "refs": evidence_refs + ["PMID:26516798"]  # TCI context review
            },
        }

    def generate_dose_response_image(self, agent: str, weight_kg: float,
                                     calculated_dose_mg_per_kg: float,
                                     patient=None) -> str:
        """
        Generate dose-response curve visualization and return as base64 string
        """
        try:
            # Create dose range for curve plotting (0.3x to 2.5x the calculated dose)
            dose_range_mg_per_kg = np.linspace(
                calculated_dose_mg_per_kg * 0.3,  # 30% of calculated dose
                calculated_dose_mg_per_kg * 2.5,  # 250% of calculated dose
                100
            )

            # Calculate response curves for the patient
            hypnosis_probabilities = []
            adverse_probabilities = []

            for dose_mg_per_kg in dose_range_mg_per_kg:
                dose_mg = dose_mg_per_kg * weight_kg

                # Calculate response using the same model
                response = self.calculate_response_probabilities(
                    dose_mg, weight_kg, agent, patient
                )

                hypnosis_probabilities.append(response['p_hypnosis'])
                adverse_probabilities.append(response['p_adverse'])

            # Calculate risk assessment for the calculated dose
            calculated_dose_mg = calculated_dose_mg_per_kg * weight_kg
            risk_assessment = self.calculate_response_probabilities(
                calculated_dose_mg, weight_kg, agent, patient
            )

            # Create the visualization
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

            # Define colors
            primary_color = '#2E86AB'  # Blue
            accent_color = '#A23B72'   # Purple/Pink
            success_color = '#F18F01'  # Orange
            warning_color = '#C73E1D'  # Red

            # Plot 1: Dose-Response Curves
            ax1.plot(dose_range_mg_per_kg, hypnosis_probabilities,
                     color=primary_color, linewidth=3, label='Hypnosis Probability', alpha=0.8)
            ax1.plot(dose_range_mg_per_kg, adverse_probabilities,
                     color=accent_color, linewidth=3, label='Adverse Event Probability', alpha=0.8)

            # Add target lines
            ax1.axhline(y=0.95, color=success_color, linestyle='--', alpha=0.7,
                        linewidth=2, label='Target Hypnosis (95%)')
            ax1.axhline(y=0.10, color=warning_color, linestyle='--', alpha=0.7,
                        linewidth=2, label='Safety Threshold (10%)')

            # Mark calculated dose
            ax1.axvline(x=calculated_dose_mg_per_kg, color='black', linestyle=':',
                        alpha=0.8, linewidth=2, label=f'Calculated Dose ({calculated_dose_mg_per_kg:.2f} mg/kg)')

            # Add dose point markers
            calc_hypnosis = risk_assessment['p_hypnosis']
            calc_adverse = risk_assessment['p_adverse']
            ax1.plot(calculated_dose_mg_per_kg, calc_hypnosis, 'o',
                     color=primary_color, markersize=10, markeredgecolor='white', markeredgewidth=2)
            ax1.plot(calculated_dose_mg_per_kg, calc_adverse, 'o',
                     color=accent_color, markersize=10, markeredgecolor='white', markeredgewidth=2)

            # Formatting
            ax1.set_xlabel('Dose (mg/kg)', fontsize=12, fontweight='bold')
            ax1.set_ylabel('Probability', fontsize=12, fontweight='bold')
            ax1.set_title(f'{agent} Dose-Response Curves\nPersonalized for Current Patient',
                          fontsize=14, fontweight='bold', pad=20)
            ax1.legend(loc='center right', frameon=True, shadow=True)
            ax1.grid(True, alpha=0.3)
            ax1.set_xlim(dose_range_mg_per_kg[0], dose_range_mg_per_kg[-1])
            ax1.set_ylim(0, 1)

            # Add text box with patient specifics if patient data available
            if patient:
                patient_info = f"Age: {patient.age}\nWeight: {patient.weight_kg} kg\nASA: {patient.asa_class}"
                ax1.text(0.02, 0.98, patient_info, transform=ax1.transAxes, fontsize=10,
                         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

            # Plot 2: Safety Window Analysis
            therapeutic_window = []
            safety_margin = []

            for i, dose_mg_per_kg in enumerate(dose_range_mg_per_kg):
                hypnosis = hypnosis_probabilities[i]
                adverse = adverse_probabilities[i]

                # Therapeutic window: difference between hypnosis and adverse probabilities
                therapeutic_window.append(hypnosis - adverse)

                # Safety margin: how far we are from 10% adverse threshold
                safety_margin.append(0.10 - adverse)

            ax2.plot(dose_range_mg_per_kg, therapeutic_window,
                     color=success_color, linewidth=3, label='Therapeutic Window\n(Hypnosis - Adverse)', alpha=0.8)
            ax2.fill_between(dose_range_mg_per_kg, 0, therapeutic_window,
                             color=success_color, alpha=0.2)

            ax2.plot(dose_range_mg_per_kg, safety_margin,
                     color=warning_color, linewidth=3, label='Safety Margin\n(10% - Adverse)', alpha=0.8)
            ax2.fill_between(dose_range_mg_per_kg, 0, safety_margin,
                             where=(np.array(safety_margin) > 0), color=warning_color, alpha=0.2)

            # Mark calculated dose
            ax2.axvline(x=calculated_dose_mg_per_kg, color='black', linestyle=':',
                        alpha=0.8, linewidth=2, label=f'Calculated Dose')

            # Calculate values at calculated dose
            calc_therapeutic = calc_hypnosis - calc_adverse
            calc_safety = 0.10 - calc_adverse

            ax2.plot(calculated_dose_mg_per_kg, calc_therapeutic, 'o',
                     color=success_color, markersize=10, markeredgecolor='white', markeredgewidth=2)
            ax2.plot(calculated_dose_mg_per_kg, calc_safety, 'o',
                     color=warning_color, markersize=10, markeredgecolor='white', markeredgewidth=2)

            # Formatting
            ax2.set_xlabel('Dose (mg/kg)', fontsize=12, fontweight='bold')
            ax2.set_ylabel('Probability Margin',
                           fontsize=12, fontweight='bold')
            ax2.set_title(f'Safety Window Analysis\nTherapeutic vs Safety Margins',
                          fontsize=14, fontweight='bold', pad=20)
            ax2.legend(loc='upper right', frameon=True, shadow=True)
            ax2.grid(True, alpha=0.3)
            ax2.axhline(y=0, color='black', linestyle='-',
                        alpha=0.5, linewidth=1)
            ax2.set_xlim(dose_range_mg_per_kg[0], dose_range_mg_per_kg[-1])

            # Add text box with calculated margins
            margin_info = f"At Calculated Dose:\nTherapeutic: {calc_therapeutic:.3f}\nSafety: {calc_safety:.3f}"
            ax2.text(0.02, 0.98, margin_info, transform=ax2.transAxes, fontsize=10,
                     verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))

            plt.tight_layout()

            # Convert plot to base64 string
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            plt.close(fig)  # Clean up memory

            return image_base64

        except Exception as e:
            print(f"Error generating dose-response image: {e}")
            return ""


class AnesthesiaDecisionSupport:
    """
    Complete decision support system using only evidence-based parameters
    """

    def __init__(self):
        self.route_selector = RouteSelector()
        self.agent_selector = AgentSelector()
        self.dose_calculator = DoseCalculator()
        self.emax_model = EmaxModel()

    def generate_plan(self, patient: PatientData, include_image: bool = False) -> Dict:
        """
        Generate complete anesthesia plan with evidence tracking
        """
        print(f"DEBUG: Starting generate_plan for patient age {patient.age}")

        # Validate patient data
        errors = patient.validate()
        print(f"DEBUG: Validation errors: {errors}")
        if errors:
            return {'status': 'error', 'errors': errors}

        plan = {
            'patient_summary': self._summarize_patient(patient),
            'timestamp': pd.Timestamp.now().isoformat(),
            'evidence_based': True
        }
        print(f"DEBUG: Initial plan created successfully")

        # Step 1: Route Selection
        print(f"DEBUG: Starting route selection")
        route_result = self.route_selector.select_route(patient)
        print(f"DEBUG: Route result type: {type(route_result)}")
        plan['route_selection'] = {
            'chosen': route_result['chosen_route'],
            'reason': route_result['reason'],
            'feasibility_assessment': route_result['feasibility'],
            'evidence': route_result['evidence_base'],
            'contributing_factors': self._extract_route_factors(route_result)
        }
        print(f"DEBUG: Route selection completed")

        # Step 2: Agent Selection
        agent_result = self.agent_selector.select_agent(
            patient,
            route_result['chosen_route']
        )
        print(
            f"DEBUG: agent_result type: {type(agent_result)}, keys: {agent_result.keys() if isinstance(agent_result, dict) else 'Not a dict'}")

        plan['agent_selection'] = {
            'chosen': agent_result['chosen_agent'],
            'score': agent_result.get('score', 0),
            'advantages': agent_result.get('advantages', []),
            'disadvantages': agent_result.get('disadvantages', []),
            'all_assessments': agent_result['all_assessments'],
            'contributing_factors': self._extract_agent_factors(agent_result)
        }

        # Step 3: Dose Calculation
        dose_result = None
        if agent_result['chosen_agent']:
            dose_result = self.dose_calculator.calculate_dose(
                agent_result['chosen_agent'],
                patient,
                route_result['chosen_route']
            )
            plan['dose_calculation'] = dose_result
            plan['dose_calculation']['contributing_factors'] = self._extract_dose_factors(
                dose_result)

        # Step 4: Risk Prediction (Emax Model with PD genetics)
        dose_response_image = None
        if route_result['chosen_route'] == 'IV' and agent_result['chosen_agent'] and dose_result:
            risk_result = self.emax_model.calculate_response_probabilities(
                dose_result['final_dose_mg'],
                patient.weight_kg,
                agent_result['chosen_agent'],
                patient  # Pass patient for PD genetics
            )

            # Generate dose-response curve image if requested
            if include_image:
                dose_response_image = self.emax_model.generate_dose_response_image(
                    agent_result['chosen_agent'],
                    patient.weight_kg,
                    dose_result['dose_mg_per_kg_on_scalar'],
                    patient
                )

            plan['risk_prediction'] = {
                'probabilities': risk_result,
                'pd_genetics_effects': risk_result.get('genetic_effects', [])
            }

            # Add image to response if generated
            if dose_response_image:
                plan['risk_prediction']['dose_response_image'] = dose_response_image

        # Add evidence summary
        plan['evidence_summary'] = self._compile_evidence_summary(plan)

        return plan

    def _summarize_patient(self, patient: PatientData) -> Dict:
        """Create patient summary including genetic profile"""

        # Summarize genetic profile
        pk_genetics = {
            'cyp2b6': patient.cyp2b6,
            'ugt1a9': patient.ugt1a9,
            'cyp3a4': patient.cyp3a4,
            'ryr1_variant': patient.ryr1_variant
        }

        pd_genetics = {
            'gabra1': patient.gabra1,
            'comt': patient.comt,
            'oprm1': patient.oprm1,
            'cacna1c': patient.cacna1c
        }

        return {
            'demographics': {
                'age': patient.age,
                'gender': patient.gender,
                'weight_kg': patient.weight_kg,
                'height_cm': patient.height_cm,
                'asa_class': patient.asa_class
            },
            'clinical_factors': {
                'cardiovascular_disease': patient.cardiovascular_disease,
                'heart_failure': patient.heart_failure,
                'reactive_airway': patient.reactive_airway,
                'copd': patient.copd
            },
            'genetics': {
                'pharmacokinetic': pk_genetics,
                'pharmacodynamic': pd_genetics
            },
            'procedure': {
                'duration_min': patient.procedure_duration_min,
                'neuromonitoring': patient.neuromonitoring
            },
        }

    def _extract_route_factors(self, route_result: Dict) -> List[Dict]:
        """Extract contributing factors from route selection"""
        factors = []

        feasibility = route_result.get('feasibility', {})
        for route, data in feasibility.items():
            for factor in data.get('factors', []):
                factors.append({
                    'category': 'Route Selection',
                    'route': route,
                    'factor': factor.get('factor', ''),
                    'impact': factor.get('impact', ''),
                    'evidence': factor.get('evidence', '')
                })

        return factors

    def _extract_agent_factors(self, agent_result: Dict) -> List[Dict]:
        """Extract contributing factors from agent selection (supports dict or list)."""
        factors: List[Dict] = []
        assessments = agent_result.get('all_assessments', {})

        # Case 1: expected dict form -> { "Propofol": {...}, "Etomidate": {...}, ... }
        if isinstance(assessments, dict):
            for agent_name, data in assessments.items():
                if not isinstance(data, dict):
                    continue
                factors.append({
                    'category': 'Agent Selection',
                    'agent': agent_name,
                    'feasible': data.get('feasible', True),
                    'contraindication': data.get('contraindication', ''),
                    'advantages': data.get('advantages', []),
                    'disadvantages': data.get('disadvantages', []),
                    'evidence': data.get('evidence', [])
                })
            return factors

        # Case 2: defensive fallback if someone ever makes it a list of dicts
        if isinstance(assessments, list):
            for data in assessments:
                if isinstance(data, dict):
                    factors.append({
                        'category': 'Agent Selection',
                        'agent': data.get('agent', ''),
                        'feasible': data.get('feasible', True),
                        'contraindication': data.get('contraindication', ''),
                        'advantages': data.get('advantages', []),
                        'disadvantages': data.get('disadvantages', []),
                        'evidence': data.get('evidence', [])
                    })
        return factors

    def _extract_dose_factors(self, dose_result: Dict) -> List[Dict]:
        """Extract contributing factors from dose calculation"""
        factors = []

        # Base dose factor
        factors.append({
            'category': 'Dose Calculation',
            'type': 'Base Dose',
            'value': dose_result.get('base_dose_per_kg', 0),
            'evidence': dose_result.get('evidence', [])
        })

        # PK genetics
        if 'pk_adjustment' in dose_result:
            adj = dose_result['pk_adjustment']
            factors.append({
                'category': 'Dose Calculation',
                'type': 'PK Genetics',
                'factor': adj.get('adjustment_factor', 1.0),
                'details': adj.get('genetic_factors', [])
            })

        # Clinical adjustments
        if 'clinical_adjustment' in dose_result:
            adj = dose_result['clinical_adjustment']
            factors.append({
                'category': 'Dose Calculation',
                'type': 'Clinical Adjustment',
                'factor': adj.get('adjustment_factor', 1.0),
                'details': adj.get('clinical_factors', [])
            })

        return factors

    def _compile_evidence_summary(self, plan: Dict) -> Dict:
        """Compile all evidence sources used in the plan"""
        evidence_sources = set()

        # Route selection evidence
        route_factors = plan.get('route_selection', {}).get(
            'contributing_factors', [])
        for factor in route_factors:
            if factor.get('evidence'):
                evidence_sources.add(factor['evidence'])

        # Agent selection evidence
        agent_factors = plan.get('agent_selection', {}).get(
            'contributing_factors', [])
        for factor in agent_factors:
            for evidence in factor.get('evidence', []):
                evidence_sources.add(evidence)

        # Dose calculation evidence
        dose_factors = plan.get('dose_calculation', {}).get(
            'contributing_factors', [])
        for factor in dose_factors:
            evidence_list = factor.get('evidence', [])
            if isinstance(evidence_list, list):
                for evidence in evidence_list:
                    evidence_sources.add(str(evidence))
            else:
                evidence_sources.add(str(evidence_list))

        return {
            'total_evidence_sources': len(evidence_sources),
            'sources': list(evidence_sources),
            'evidence_grade': 'A/B - Peer-reviewed literature only'
        }


class AnesthesiaCalculationAPIView(APIView):
    """
    API view for anesthesia dosage calculation and planning.
    Saves dose-response PNG under {BASE_DIR}/data/ and returns a '/data/<file>.png' URL.
    """

    # ---- helpers -------------------------------------------------------------

    def _ensure_data_dir(self) -> str:
        """
        Ensure a {BASE_DIR}/data directory exists and return its absolute path.
        """
        base_dir = getattr(settings, "BASE_DIR", os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir

    def _save_png_from_b64(self, img_b64: str, request) -> str:
        """
        Takes a base64 (no header) PNG string, writes it to {BASE_DIR}/data, and returns the absolute URL.
        """
        if not img_b64:
            return ""

        # Some libs prepend "data:image/png;base64,", strip if present
        if "," in img_b64 and img_b64.strip().startswith("data:"):
            img_b64 = img_b64.split(",", 1)[1]

        try:
            png_bytes = base64.b64decode(img_b64, validate=True)
        except Exception:
            return ""

        data_dir = self._ensure_data_dir()
        # unique, readable filename
        fname = f"dose_response_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
        fpath = os.path.join(data_dir, fname)

        with open(fpath, "wb") as f:
            f.write(png_bytes)

        # Build absolute URL like https://maindomain/data/imagename.png
        # You can adjust the '/data/' prefix if you mount it differently in urls.py
        return request.build_absolute_uri(f"/data/{fname}")

    # ---- API methods --------------------------------------------------------

    def post(self, request):
        """
        Calculate anesthesia dosages and return personalized recommendations.
        Also persists the dose-response image to /data and returns its URL.
        """
        try:
            # Extract query_type and user_input from request
            query_type = request.data.get('query_type', 'user_query')
            user_input = request.data.get('user_input', {})

            # 1) Validate input
            serializer = PatientDataSerializer(data=user_input)
            if not serializer.is_valid():
                return Response({
                    'status': 'error',
                    'message': 'Invalid patient data',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            vd = dict(serializer.validated_data)

            # 2) Always calculate ASA class in backend (ignore client input)
            asa_val, asa_reason = calculate_asa_class(
                age=vd['age'],
                weight_kg=vd['weight_kg'],
                height_cm=vd['height_cm'],
                cardiovascular_disease=vd.get(
                    'cardiovascular_disease', False),
                heart_failure=vd.get('heart_failure', False),
                reactive_airway=vd.get('reactive_airway', False),
                copd=vd.get('copd', False),
                diabetes=vd.get('diabetes', False),
                hypertension=vd.get('hypertension', False),
                smoking_status=vd.get('smoking_status', 'never'),
                alcohol_use=vd.get('alcohol_use', 'none'),
            )
            vd['asa_class'] = asa_val

            # 3) Build PatientData
            patient = PatientData(
                age=vd['age'],
                weight_kg=vd['weight_kg'],
                height_cm=vd['height_cm'],
                gender=vd['gender'],
                asa_class=vd['asa_class'],
                cardiovascular_disease=vd.get('cardiovascular_disease', False),
                heart_failure=vd.get('heart_failure', False),
                reactive_airway=vd.get('reactive_airway', False),
                copd=vd.get('copd', False),
                diabetes=vd.get('diabetes', False),
                hypertension=vd.get('hypertension', False),
                smoking_status=vd.get('smoking_status', 'never'),
                alcohol_use=vd.get('alcohol_use', 'none'),
                ryr1_variant=vd.get('ryr1_variant', 'Normal'),
                cyp2b6=vd.get('cyp2b6', 'NM'),
                ugt1a9=vd.get('ugt1a9', 'normal'),
                cyp3a4=vd.get('cyp3a4', 'NM'),
                cyp2c9=vd.get('cyp2c9', 'NM'),
                gabra1=vd.get('gabra1', 'rs4263535:A/A'),
                comt=vd.get('comt', 'Val158Met:Val/Val'),
                oprm1=vd.get('oprm1', 'A118G:A/A'),
                cacna1c=vd.get('cacna1c', 'rs1006737:G/G'),
                procedure_duration_min=vd['procedure_duration_min'],
                neuromonitoring=vd.get('neuromonitoring', False),
            )

            # 4) Domain validation
            validation_errors = patient.validate()
            if validation_errors:
                return Response({
                    'status': 'error',
                    'message': 'Patient validation failed',
                    'errors': validation_errors
                }, status=status.HTTP_400_BAD_REQUEST)

            # 5) Generate plan (with image)
            decision_support = AnesthesiaDecisionSupport()
            include_image = vd.get('include_dose_response_image', True)
            plan = decision_support.generate_plan(
                patient, include_image=include_image)

            if plan.get('status') == 'error':
                return Response({
                    'status': 'error',
                    'message': 'Plan generation failed',
                    'errors': plan.get('errors', [])
                }, status=status.HTTP_400_BAD_REQUEST)

            # 6) Persist image to /data and inject URL
            image_url = ""
            if include_image:
                img_b64 = (plan.get('risk_prediction') or {}).get(
                    'dose_response_image')
                if img_b64:
                    image_url = self._save_png_from_b64(img_b64, request)
                    # remove base64 to keep response small
                    try:
                        plan['risk_prediction'].pop(
                            'dose_response_image', None)
                    except Exception:
                        pass

                    # add URL reference
                    if image_url:
                        plan['risk_prediction']['dose_response_image_url'] = image_url

            # 7) Shape final response
            bmi_val = round(patient.weight_kg /
                            ((patient.height_cm / 100) ** 2), 2)
            response_data = {
                "status": "success",
                "message": "Anesthesia plan generated successfully",
                "patient_input": {
                    "demographics": {
                        "age": patient.age,
                        "weight_kg": patient.weight_kg,
                        "height_cm": patient.height_cm,
                        "gender": patient.gender,
                        "bmi": bmi_val
                    },
                    "clinical_factors": {
                        "asa_class": patient.asa_class,
                        "cardiovascular_disease": patient.cardiovascular_disease,
                        "heart_failure": patient.heart_failure,
                        "reactive_airway": patient.reactive_airway,
                        "copd": patient.copd,
                        "diabetes": patient.diabetes,
                        "hypertension": patient.hypertension,
                        "smoking_status": patient.smoking_status,
                        "alcohol_use": patient.alcohol_use
                    },
                    "genetic_markers": {
                        "pharmacokinetic": {
                            "ryr1_variant": patient.ryr1_variant,
                            "cyp2b6": patient.cyp2b6,
                            "ugt1a9": patient.ugt1a9,
                            "cyp3a4": patient.cyp3a4,
                            "cyp2c9": patient.cyp2c9
                        },
                        "pharmacodynamic": {
                            "gabra1": patient.gabra1,
                            "comt": patient.comt,
                            "oprm1": patient.oprm1,
                            "cacna1c": patient.cacna1c
                        }
                    },
                    "procedure": {
                        "duration_min": patient.procedure_duration_min,
                        "neuromonitoring": patient.neuromonitoring
                    }
                },
                "anesthesia_plan": plan,
                "evidence_based": True,
                "timestamp": plan.get("timestamp", "")
            }

            # If we didn’t have an image, still indicate availability
            response_data["anesthesia_plan"]["risk_prediction_image"] = {
                "available": bool(image_url),
                "url": image_url or None
            }

            # Create EventLog entry
            event_log = EventLog.objects.create(
                event_type=query_type,
                user_input=user_input,
                generated_result=response_data
            )

            # Add session_id to response
            response_data['session_id'] = str(event_log.session_id)

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            import traceback
            return Response({
                'status': 'error',
                'message': f'Internal server error: {str(e)}',
                'trace': traceback.format_exc()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request):
        return Response({
            'status': 'success',
            'message': 'Anesthesia Calculation API',
            'description': 'Calculates a personalized anesthesia plan; saves dose-response PNG to /data and returns its URL.',
            'image_serving': 'This endpoint writes files to {BASE_DIR}/data and returns /data/<filename>.png URLs.'
        }, status=status.HTTP_200_OK)
