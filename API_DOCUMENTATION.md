# AnesysIQ: Personalized Anesthesia Calculation API

## Frontend Developer Guide

---

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [API Endpoints](#api-endpoints)
3. [Request Format](#request-format)
4. [Response Format](#response-format)
5. [Input Parameters](#input-parameters)
6. [Error Handling](#error-handling)
7. [Code Examples](#code-examples)
8. [Genetic Markers Reference](#genetic-markers-reference)
9. [Image Handling](#image-handling)
10. [Testing](#testing)

---

## 🚀 Quick Start

The **AnesysIQ API** calculates personalized anesthesia recommendations based on patient demographics, clinical factors, and genetic markers.

### Base URL

```
http://localhost:8000/api/calculate/
```

### Quick Example

```javascript
const patientData = {
  // Required demographics
  age: 45,
  weight_kg: 70.0,
  height_cm: 175.0,
  gender: 'M',

  // Required clinical factors
  cardiovascular_disease: false,
  heart_failure: false,
  reactive_airway: false,
  copd: false,
  procedure_duration_min: 120,

  // Optional parameters (will use defaults if not provided)
  diabetes: true,
  hypertension: true,
  smoking_status: 'former',
};

fetch('http://localhost:8000/api/calculate/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(patientData),
})
  .then((response) => response.json())
  .then((data) => console.log(data));
```

### Key Features

- **Evidence-based recommendations** with 20+ peer-reviewed sources
- **Pharmacogenetic integration** with 9 genetic markers
- **Real-time dose-response modeling** with safety predictions
- **Dose-response curve generation** saved as PNG files
- **Complete evidence tracking** with PMID references

---

## 🔗 API Endpoints

### Primary Endpoint

**POST** `/api/anesthesia-calculation/`

**Content-Type:** `application/json`

**Purpose:** Generate personalized anesthesia recommendations

**GET** `/api/anesthesia-calculation/`

**Purpose:** Get API information and documentation

---

## 📝 Request Format

### Required Parameters

All requests must include these fields:

```json
{
  "age": 45, // Integer: 18-95 years
  "weight_kg": 70.0, // Float: 30-220 kg
  "height_cm": 175.0, // Float: 120-220 cm
  "gender": "M", // String: "M" or "F"
  "cardiovascular_disease": false, // Boolean
  "heart_failure": false, // Boolean
  "reactive_airway": false, // Boolean
  "copd": false, // Boolean
  "procedure_duration_min": 120 // Integer: 1-1440 minutes
}
```

### Optional Parameters

```json
{
  // Clinical factors (defaults to false/none if not provided)
  "asa_class": 2, // Integer: 1-5 (auto-calculated if missing)
  "diabetes": false, // Boolean (default: false)
  "hypertension": false, // Boolean (default: false)
  "smoking_status": "never", // String: "never"|"former"|"current"
  "alcohol_use": "none", // String: "none"|"social"|"heavy"
  "neuromonitoring": false, // Boolean (default: false)

  // Pharmacokinetic genetics (defaults to normal/NM)
  "ryr1_variant": "Normal", // String: "Normal"|"Variant"
  "cyp2b6": "NM", // String: "PM"|"IM"|"NM"|"RM"
  "ugt1a9": "normal", // String: "decreased"|"normal"|"increased"
  "cyp3a4": "NM", // String: "PM"|"IM"|"NM"|"RM"
  "cyp2c9": "NM", // String: "PM"|"IM"|"NM"|"RM"

  // Pharmacodynamic genetics (defaults provided)
  "gabra1": "rs4263535:A/A", // String: see genetic markers section
  "comt": "Val158Met:Val/Val", // String: see genetic markers section
  "oprm1": "A118G:A/A", // String: see genetic markers section
  "cacna1c": "rs1006737:G/G", // String: see genetic markers section

  // Image generation
  "include_dose_response_image": true // Boolean: generate dose-response curve
}
```

---

## 📊 Response Format

### Success Response (HTTP 200)

```json
{
  "status": "success",
  "message": "Anesthesia plan generated successfully",
  "patient_input": {
    "demographics": {
      "age": 45,
      "weight_kg": 70.0,
      "height_cm": 175.0,
      "gender": "M",
      "bmi": 22.9
    },
    "clinical_factors": {
      "asa_class": 2,
      "cardiovascular_disease": false,
      "heart_failure": false,
      "reactive_airway": false,
      "copd": false,
      "diabetes": true,
      "hypertension": true,
      "smoking_status": "former",
      "alcohol_use": "social"
    },
    "genetic_markers": {
      "pharmacokinetic": {
        "ryr1_variant": "Normal",
        "cyp2b6": "NM",
        "ugt1a9": "normal",
        "cyp3a4": "NM",
        "cyp2c9": "NM"
      },
      "pharmacodynamic": {
        "gabra1": "rs4263535:A/A",
        "comt": "Val158Met:Val/Val",
        "oprm1": "A118G:A/A",
        "cacna1c": "rs1006737:G/G"
      }
    },
    "procedure": {
      "duration_min": 120,
      "neuromonitoring": false
    }
  },
  "anesthesia_plan": {
    "route_selection": {
      "chosen": "IV",
      "reason": "Standard choice for adult patient without contraindications",
      "feasibility_assessment": {
        "IV": {
          "feasible": true,
          "factors": [...],
          "evidence": [...]
        },
        "Inhalation": {
          "feasible": true,
          "factors": [...],
          "evidence": [...]
        }
      },
      "evidence": [...],
      "contributing_factors": [...]
    },
    "agent_selection": {
      "chosen": "Propofol",
      "score": 8.5,
      "advantages": [
        {
          "factor": "Reduced PONV and smoother recovery vs volatiles",
          "magnitude": "Meta-analysis shows lower early/late PONV with propofol TIVA",
          "evidence": ["PMID:25296857"]
        }
      ],
      "disadvantages": [
        {
          "factor": "Hypotension risk in cardiovascular patients",
          "magnitude": "15-25% incidence of significant hypotension",
          "evidence": ["PMID:35489305"]
        }
      ],
      "all_assessments": {},
      "contributing_factors": []
    },
    "dose_calculation": {
      "agent": "Propofol",
      "route": "IV",
      "final_dose_mg": 140.0,
      "dose_mg_per_kg_on_scalar": 2.0,
      "base_dose_mg_per_kg": 2.0,
      "weight_scalar_kg": 70.0,
      "units": "mg",
      "pk_adjustments": [
        {
          "factor": "CYP2B6 Normal Metabolizer",
          "adjustment": 1.0,
          "evidence": ["PMID:38135504"]
        }
      ],
      "clinical_adjustments": [
        {
          "factor": "ASA II patient",
          "adjustment": 0.95,
          "evidence": ["ASA-Guidelines"]
        }
      ],
      "contributing_factors": []
    },
    "risk_prediction": {
      "probabilities": {
        "p_hypnosis": 0.85,
        "p_adverse": 0.12,
        "therapeutic_index": 7.08
      },
      "pd_genetics_effects": [
        {
          "gene": "GABRA1",
          "variant": "rs4263535:A/A",
          "effect": "Normal sensitivity (reference)",
          "ec50_adjustment": 1.0
        }
      ]
    },
    "evidence_summary": {
      "total_evidence_sources": 15,
      "sources": [
        "PMID:25296857",
        "PMID:35489305",
        "PMID:15184982",
        "PMID:35173461"
      ],
      "evidence_grade": "A/B - Peer-reviewed literature only",
      "categories": {
        "pharmacokinetics": 8,
        "pharmacodynamics": 5,
        "clinical_guidelines": 2
      }
    },
    "timestamp": "2025-09-15T10:30:00.000Z"
  },
  "evidence_based": true,
  "risk_prediction_image": {
    "available": true,
    "url": "/data/dose_response_20250915T103000_abc123.png"
  },
  "timestamp": "2025-09-15T10:30:00.000Z"
}
```

---

## 📝 Input Parameters

### Parameter Reference Table

| Parameter                     | Type    | Required | Range/Values                       | Default             | Description                     |
| ----------------------------- | ------- | -------- | ---------------------------------- | ------------------- | ------------------------------- |
| **Demographics**              |
| `age`                         | Integer | ✅       | 18-95                              | -                   | Patient age in years            |
| `weight_kg`                   | Float   | ✅       | 30-220                             | -                   | Weight in kilograms             |
| `height_cm`                   | Float   | ✅       | 120-220                            | -                   | Height in centimeters           |
| `gender`                      | String  | ✅       | "M", "F"                           | -                   | Patient gender                  |
| **Clinical Factors**          |
| `cardiovascular_disease`      | Boolean | ✅       | true/false                         | -                   | Cardiovascular disease presence |
| `heart_failure`               | Boolean | ✅       | true/false                         | -                   | Heart failure presence          |
| `reactive_airway`             | Boolean | ✅       | true/false                         | -                   | Reactive airway/asthma          |
| `copd`                        | Boolean | ✅       | true/false                         | -                   | COPD presence                   |
| `procedure_duration_min`      | Integer | ✅       | 1-1440                             | -                   | Procedure duration in minutes   |
| `asa_class`                   | Integer | ❌       | 1-5                                | Auto-calculated     | ASA Physical Status             |
| `diabetes`                    | Boolean | ❌       | true/false                         | false               | Diabetes presence               |
| `hypertension`                | Boolean | ❌       | true/false                         | false               | Hypertension presence           |
| `smoking_status`              | String  | ❌       | "never", "former", "current"       | "never"             | Smoking history                 |
| `alcohol_use`                 | String  | ❌       | "none", "social", "heavy"          | "none"              | Alcohol consumption             |
| `neuromonitoring`             | Boolean | ❌       | true/false                         | false               | Neuromonitoring use             |
| **Pharmacokinetic Genetics**  |
| `ryr1_variant`                | String  | ❌       | "Normal", "Variant"                | "Normal"            | Malignant hyperthermia risk     |
| `cyp2b6`                      | String  | ❌       | "PM", "IM", "NM", "RM"             | "NM"                | CYP2B6 metabolizer status       |
| `ugt1a9`                      | String  | ❌       | "decreased", "normal", "increased" | "normal"            | UGT1A9 function                 |
| `cyp3a4`                      | String  | ❌       | "PM", "IM", "NM", "RM"             | "NM"                | CYP3A4 metabolizer status       |
| `cyp2c9`                      | String  | ❌       | "PM", "IM", "NM", "RM"             | "NM"                | CYP2C9 metabolizer status       |
| **Pharmacodynamic Genetics**  |
| `gabra1`                      | String  | ❌       | See genetic markers section        | "rs4263535:A/A"     | GABA-A receptor α1              |
| `comt`                        | String  | ❌       | See genetic markers section        | "Val158Met:Val/Val" | COMT enzyme                     |
| `oprm1`                       | String  | ❌       | See genetic markers section        | "A118G:A/A"         | Opioid receptor                 |
| `cacna1c`                     | String  | ❌       | See genetic markers section        | "rs1006737:G/G"     | Calcium channel                 |
| **Image Generation**          |
| `include_dose_response_image` | Boolean | ❌       | true/false                         | true                | Generate dose-response curve    |

### Metabolizer Status Guide

- **PM** (Poor Metabolizer): Slow drug clearance, may need dose reduction
- **IM** (Intermediate): Moderately reduced clearance
- **NM** (Normal): Standard clearance and dosing
- **RM** (Rapid): Fast clearance, may need dose increase

---

## ⚠️ Error Handling

### Validation Errors (HTTP 400)

```json
{
  "status": "error",
  "message": "Invalid patient data",
  "errors": {
    "age": ["Ensure this value is greater than or equal to 18."],
    "cyp2b6": [
      "Select a valid choice. 'XX' is not one of the available choices."
    ],
    "weight_kg": ["Ensure this value is less than or equal to 220."]
  }
}
```

### Common Validation Issues

| Field       | Common Errors              | Solution                           |
| ----------- | -------------------------- | ---------------------------------- |
| `age`       | Must be 18-95              | Use valid age range                |
| `weight_kg` | Must be 30-220             | Check weight units (kg not lbs)    |
| `height_cm` | Must be 120-220            | Check height units (cm not inches) |
| `gender`    | Must be "M" or "F"         | Use exact string values            |
| `cyp2b6`    | Invalid metabolizer status | Use: "PM", "IM", "NM", "RM"        |
| `gabra1`    | Invalid variant format     | Use exact format: "rs4263535:A/A"  |

### Server Errors (HTTP 500)

```json
{
  "status": "error",
  "message": "Internal server error: calculation failed",
  "trace": "..."
}
```

---

## 💻 Code Examples

### JavaScript/React Example

```javascript
import React, { useState } from 'react';

const AnesthesiaCalculator = () => {
  const [patient, setPatient] = useState({
    age: '',
    weight_kg: '',
    height_cm: '',
    gender: '',
    cardiovascular_disease: false,
    heart_failure: false,
    reactive_airway: false,
    copd: false,
    procedure_duration_min: '',
  });

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const calculateAnesthesia = async () => {
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/calculate/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ...patient,
          age: parseInt(patient.age),
          weight_kg: parseFloat(patient.weight_kg),
          height_cm: parseFloat(patient.height_cm),
          procedure_duration_min: parseInt(patient.procedure_duration_min),
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setResult(data);
        console.log(
          'Recommended agent:',
          data.anesthesia_plan.agent_selection.chosen
        );
        console.log(
          'Recommended dose:',
          data.anesthesia_plan.dose_calculation.final_dose_mg
        );
      } else {
        console.error('API Error:', data.errors);
      }
    } catch (error) {
      console.error('Network Error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2>Anesthesia Calculator</h2>
      {/* Add your form inputs here */}
      <button onClick={calculateAnesthesia} disabled={loading}>
        {loading ? 'Calculating...' : 'Calculate Anesthesia Plan'}
      </button>

      {result && (
        <div>
          <h3>Results:</h3>
          <p>Route: {result.anesthesia_plan.route_selection.chosen}</p>
          <p>Agent: {result.anesthesia_plan.agent_selection.chosen}</p>
          <p>
            Dose: {result.anesthesia_plan.dose_calculation.final_dose_mg} mg
          </p>
          <p>Evidence-based: {result.evidence_based ? 'Yes' : 'No'}</p>
        </div>
      )}
    </div>
  );
};

export default AnesthesiaCalculator;
```

### Python Example

```python
import requests
import json

def calculate_anesthesia_plan(patient_data):
    """Calculate anesthesia plan for a patient"""
    url = "http://localhost:8000/api/calculate/"

    try:
        response = requests.post(
            url,
            json=patient_data,
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code == 200:
            result = response.json()
            return {
                'success': True,
                'data': result
            }
        else:
            return {
                'success': False,
                'error': response.json()
            }

    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': str(e)
        }

# Example usage
patient = {
    "age": 45,
    "weight_kg": 70.0,
    "height_cm": 175.0,
    "gender": "M",
    "cardiovascular_disease": False,
    "heart_failure": False,
    "reactive_airway": False,
    "copd": False,
    "diabetes": True,
    "hypertension": True,
    "smoking_status": "former",
    "alcohol_use": "social",
    "procedure_duration_min": 120,
    "cyp2b6": "IM",  # Intermediate metabolizer
    "gabra1": "rs4263535:G/G"  # Increased sensitivity variant
}

result = calculate_anesthesia_plan(patient)

if result['success']:
    plan = result['data']['anesthesia_plan']
    print(f"Recommended route: {plan['route_selection']['chosen']}")
    print(f"Recommended agent: {plan['agent_selection']['chosen']}")
    print(f"Recommended dose: {plan['dose_calculation']['final_dose_mg']} mg")
    print(f"Evidence sources: {len(plan['evidence_summary']['sources'])}")
else:
    print(f"Error: {result['error']}")
```

### cURL Example

```bash
curl -X POST http://localhost:8000/api/calculate/ \
  -H "Content-Type: application/json" \
  -d '{
    "age": 65,
    "weight_kg": 80.0,
    "height_cm": 170.0,
    "gender": "F",
    "cardiovascular_disease": true,
    "heart_failure": false,
    "reactive_airway": false,
    "copd": false,
    "diabetes": true,
    "hypertension": true,
    "smoking_status": "former",
    "alcohol_use": "none",
    "procedure_duration_min": 90,
    "asa_class": 3,
    "cyp2b6": "PM",
    "include_dose_response_image": true
  }'
```

---

## 🧬 Genetic Markers Reference

### Pharmacokinetic (PK) Genetics

These affect how quickly the body processes anesthetic drugs:

#### CYP2B6 - Propofol/Ketamine Metabolism

```
Valid values: "PM", "IM", "NM", "RM"
Effect: Affects drug clearance rates
Evidence: PMID:38135504, PMID:37227973
```

#### UGT1A9 - Propofol Glucuronidation

```
Valid values: "decreased", "normal", "increased"
Effect: Primary propofol elimination pathway (70% of metabolism)
Evidence: PMID:15184982
```

#### CYP3A4 - Ketamine Metabolism

```
Valid values: "PM", "IM", "NM", "RM"
Effect: Primary ketamine N-demethylation pathway
Evidence: PMID:12065445
```

#### CYP2C9 - Minor Metabolic Pathway

```
Valid values: "PM", "IM", "NM", "RM"
Effect: Minor contribution to anesthetic metabolism
Evidence: PMID:29992157
```

#### RYR1 - Malignant Hyperthermia Risk

```
Valid values: "Normal", "Variant"
Effect: "Variant" contraindicates inhalational agents
Evidence: MHAUS Guidelines
```

### Pharmacodynamic (PD) Genetics

These affect drug sensitivity and response:

#### GABRA1 - GABA-A Receptor α1 Subunit

```
Valid values:
- "rs4263535:G/G" (increased sensitivity, 15% lower EC50)
- "rs4263535:A/G" (moderately increased sensitivity, 7% lower EC50)
- "rs4263535:A/A" (normal sensitivity, reference)

Effect: Affects propofol/etomidate sensitivity
Evidence: PMID:35173461
```

#### COMT - Catechol-O-Methyltransferase

```
Valid values:
- "Val158Met:Met/Met" (reduced enzyme activity, increased sensitivity)
- "Val158Met:Val/Met" (intermediate activity)
- "Val158Met:Val/Val" (normal activity, reference)

Effect: Affects stress response and anesthetic requirements
Evidence: PMID:17185601
```

#### OPRM1 - Opioid Receptor μ1

```
Valid values:
- "A118G:G/G" (reduced sensitivity, higher requirements)
- "A118G:A/G" (intermediate sensitivity)
- "A118G:A/A" (normal sensitivity, reference)

Effect: Affects opioid analgesic sensitivity
Evidence: PMID:19706592
```

#### CACNA1C - Calcium Channel α1C Subunit

```
Valid values:
- "rs1006737:A/A" (reduced calcium channel sensitivity, 10% higher EC50)
- "rs1006737:A/G" (moderately reduced sensitivity, 5% higher EC50)
- "rs1006737:G/G" (normal sensitivity, reference)

Effect: Affects cardiovascular response to anesthetics
Evidence: PMID:25533539
```

---

## 🖼️ Image Handling

### Dose-Response Curve Generation

The API can generate dose-response curves showing the relationship between dose and probability of hypnosis/adverse events.

#### Request Image Generation

```json
{
  "include_dose_response_image": true
  // ... other patient parameters
}
```

#### Image Response Format

The API saves images to the `/data` directory and returns the URL:

```json
{
  "risk_prediction_image": {
    "available": true,
    "url": "/data/dose_response_20250915T103000_abc123.png"
  }
}
```

#### Accessing Images

Images are served as static files from the Django backend:

```javascript
// Frontend code to display the image
const imageUrl = `http://localhost:8000${response.risk_prediction_image.url}`;
document.getElementById('dose-response-chart').src = imageUrl;
```

#### Image Properties

- **Format**: PNG
- **Size**: Approximately 800x600 pixels
- **Content**: Dose-response curves with genetic adjustments
- **Filename**: Timestamped with unique ID
- **Storage**: Saved to `/data` directory on backend

---

## 🧪 Testing

### Test Data Sets

#### Minimal Required Request

```json
{
  "age": 30,
  "weight_kg": 70.0,
  "height_cm": 175.0,
  "gender": "M",
  "cardiovascular_disease": false,
  "heart_failure": false,
  "reactive_airway": false,
  "copd": false,
  "procedure_duration_min": 60
}
```

#### Complex Patient with Genetics

```json
{
  "age": 75,
  "weight_kg": 65.0,
  "height_cm": 165.0,
  "gender": "F",
  "asa_class": 3,
  "cardiovascular_disease": true,
  "heart_failure": true,
  "reactive_airway": false,
  "copd": false,
  "diabetes": true,
  "hypertension": true,
  "smoking_status": "former",
  "alcohol_use": "none",
  "procedure_duration_min": 180,
  "neuromonitoring": true,
  "ryr1_variant": "Variant",
  "cyp2b6": "PM",
  "ugt1a9": "decreased",
  "cyp3a4": "IM",
  "cyp2c9": "PM",
  "gabra1": "rs4263535:G/G",
  "comt": "Val158Met:Met/Met",
  "oprm1": "A118G:G/G",
  "cacna1c": "rs1006737:A/A",
  "include_dose_response_image": true
}
```

### Testing Checklist

- [ ] Test with minimal required parameters
- [ ] Test with all optional parameters
- [ ] Test validation errors (invalid ages, weights, etc.)
- [ ] Test genetic variant combinations
- [ ] Test image generation on/off
- [ ] Test server error handling
- [ ] Test response time (should be < 5 seconds)
- [ ] Verify evidence sources in responses
- [ ] Check image URL accessibility

### Development Environment

```bash
# Start the Django development server
python manage.py runserver

# Test the API endpoint
curl -X GET http://localhost:8000/api/calculate/

# Run Django tests (if available)
python manage.py test
```

---

## 📊 Response Examples

### Successful Calculation Response

```json
{
  "status": "success",
  "message": "Anesthesia plan generated successfully",
  "patient_input": {
    "demographics": {
      "age": 45,
      "weight_kg": 70.0,
      "height_cm": 175.0,
      "gender": "M",
      "bmi": 22.9
    }
  },
  "anesthesia_plan": {
    "route_selection": {
      "chosen": "IV"
    },
    "agent_selection": {
      "chosen": "Propofol"
    },
    "dose_calculation": {
      "final_dose_mg": 140.0,
      "agent": "Propofol"
    },
    "risk_prediction": {
      "probabilities": {
        "p_hypnosis": 0.95,
        "p_adverse": 0.08
      }
    }
  },
  "evidence_based": true
}
```

---

**Last Updated**: September 15, 2025  
**API Version**: 2.0  
**Backend Framework**: Django REST Framework  
**Evidence Sources**: 20+ peer-reviewed publications
