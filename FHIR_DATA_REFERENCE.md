# FHIR Data Reference - Complete Clinical Timeline

## FHIR Server: https://r4.smarthealthit.org

---

## 1. PRIMARY DEMO PATIENT: Raeann O'Kon ("Maria")

### Patient Demographics
| Field | Value |
|-------|-------|
| **Patient ID** | `881f534f-d041-425d-a542-cbf669f43e18` |
| **Name** | Mrs. Raeann O'Kon (maiden: Blick) |
| **DOB** | 1968-10-09 |
| **Gender** | Female |
| **Race** | Black or African American |
| **Ethnicity** | Not Hispanic or Latino |
| **Birth Sex** | F |
| **Birthplace** | Kingston, Jamaica |
| **Language** | French |
| **Marital Status** | Married |
| **Address** | 498 Stamm Track Suite 84, Lawrence, MA 01840 |
| **Phone** | 555-743-6920 |
| **MRN** | 9e8ba712-5bbf-4e3c-8946-b66032309cfc |
| **Mother's Maiden Name** | Eulalia Conn |
| **Coverage/Insurance** | None on record |
| **Related Persons** | None on record |

---

### Conditions / Diagnoses (22 total)

#### Active Chronic Conditions
| Resource ID | Condition | SNOMED Code | Onset Date |
|-------------|-----------|-------------|------------|
| `abc9ea4f-6eb2-44b6-8f02-e16cb056b5ca` | **Diabetes** (Type 2) | 44054006 | 2003-01-15 |
| `07c4fa62-b6c4-44c0-9443-6f6e59dc47cb` | **Hypertension** | 38341003 | 2003-01-15 |
| `a5f762c5-bcae-4e93-a740-511b293e1cda` | **Metabolic syndrome X** | 237602007 | 2006-01-18 |
| `594d70c6-bc90-4e27-864a-0f9d6f77c2bf` | **Hypertriglyceridemia** | 302870006 | 2006-01-18 |
| `f132c368-e808-466c-b0a9-e893b6e83bda` | **Anemia** | 271737000 | 2006-01-18 |
| `e0650347-86bd-4a23-ade4-06f8a560d918` | **Hyperglycemia** | 80394007 | 2008-10-15 |
| `d15cff3f-c462-4e4e-ba24-c177d027872b` | **Prediabetes** | 15777000 | 2010-10-20 |
| `70758a4d-cacc-4206-9621-571dd6de6528` | **Diabetic neuropathy** (Type 2) | 368581000119106 | 2010-10-20 |

#### Pregnancy-Related Conditions (all resolved)
| Resource ID | Condition | SNOMED Code | Onset | Abatement |
|-------------|-----------|-------------|-------|-----------|
| `ecfad91f-5075-488a-a86c-7c766b41a21c` | Normal pregnancy | 72892002 | 2013-09-25 | 2013-10-09 |
| `98019b0c-54c1-4093-9755-7d87ae2c2649` | Blighted ovum | 35999006 | 2013-09-25 | 2013-10-09 |
| `c38df46a-5d39-4920-9664-38c9044454c4` | **Miscarriage in first trimester** | 19169002 | 2013-09-25 | N/A (active) |
| `5d3da01a-5fe6-466e-bcfd-fc98a6f3ba5a` | Normal pregnancy | 72892002 | 2014-10-22 | 2014-10-29 |
| `0e34e23a-c09b-458d-879e-968f2a235808` | Fetus with unknown complication | 156073000 | 2014-10-22 | 2014-10-29 |
| `d96d2f80-5d7c-47a1-b7a6-557a1d173c13` | Normal pregnancy | 72892002 | 2015-12-23 | 2016-01-13 |
| `9b38e621-f8ba-403c-abc3-8e538168bb5f` | Normal pregnancy | 72892002 | 2016-08-10 | 2016-08-17 |
| `d3687855-8d9a-4630-bffc-4fdb72be4daa` | Blighted ovum | 35999006 | 2016-08-10 | 2016-08-17 |
| `60430126-0acb-4c15-9284-74db62005c7c` | Normal pregnancy | 72892002 | 2018-08-29 | 2018-09-05 |
| `9de83c01-5c23-4169-a4d6-bc862178e6d3` | Fetus with unknown complication | 156073000 | 2018-08-29 | 2018-09-05 |
| `9f80e77a-1580-480f-a4e5-48ec05ca4354` | **Normal pregnancy (carried to term)** | 72892002 | 2018-12-12 | 2019-07-24 |

#### Other Resolved Conditions
| Resource ID | Condition | SNOMED Code | Onset | Abatement |
|-------------|-----------|-------------|-------|-----------|
| `6f806e9d-3ab6-4323-b67b-e350a5a2b205` | Fracture of ankle | 16114001 | 2015-01-20 | 2015-02-19 |
| `faee62ba-e02a-4077-8827-ea09657fdc0f` | Viral sinusitis | 444814009 | 2017-07-29 | 2017-08-12 |
| `155d8cb7-02be-473a-94c0-9ee2f8bac581` | Viral sinusitis | 444814009 | 2020-07-04 | 2020-07-11 |

---

### Medications (7 total)

| Resource ID | Medication | RxNorm Code | Authored | Status | Reason |
|-------------|-----------|-------------|----------|--------|--------|
| `91a9e5d7-4e57-4879-9340-611acb049f8f` | **Hydrochlorothiazide 25 MG** | 316049 | 2003-01-15 | **active** | Hypertension |
| `f6255a19-d66f-41df-a70f-42a68ae2b36f` | **Metformin ER 500 MG** | 860975 | 2006-01-18 | **active** | Diabetes |
| `dbf3522b-8381-4621-9258-220860bb334c` | Camila 28 Day Pack (norethindrone) | 748962 | 2010-08-09 | stopped | Contraception |
| `9a831264-c383-4b1e-aeca-e4f1a51853d7` | Jolivette 28 Day Pack (norethindrone) | 757594 | 2012-07-29 | stopped | Contraception |
| `58647b09-c966-475f-ad01-8ff87e9e7f8a` | Meperidine HCl 50 MG Oral Tablet | 861467 | 2015-01-20 | stopped | Ankle fracture pain |
| `0ccadbb6-25ad-4844-a5bb-4a311a032cfc` | Naproxen sodium 220 MG Oral Tablet | 849574 | 2015-01-20 | stopped | Ankle fracture pain |
| `43a0af50-1d82-46d1-93b9-a0ffaad86eb4` | Camila 28 Day Pack (norethindrone) | 748962 | 2016-08-17 | stopped | Contraception |

---

### Key Observations - Trends Over Time

#### Blood Pressure Trend (LOINC: 55284-4)
| Date | Systolic (mm[Hg]) | Diastolic (mm[Hg]) | Assessment |
|------|-------------------|---------------------|------------|
| 2012-10-24 | **160.5** | **105.8** | Stage 2 HTN |
| 2014-10-29 | **167.0** | **117.3** | Stage 2 HTN (worsening) |
| 2016-11-02 | **148.0** | **103.7** | Stage 2 HTN |
| 2018-10-10 | **140.2** | **100.2** | Stage 2 HTN |
| 2019-10-16 | **170.3** | **97.6** | Stage 2 HTN (spike) |
| 2020-10-21 | **163.2** | **110.6** | Stage 2 HTN |

> **Key finding:** BP consistently elevated, never controlled below 140/90 despite hydrochlorothiazide. Poorly controlled hypertension throughout pregnancy period.

#### Glucose Trend (LOINC: 2339-0)
| Date | Glucose (mg/dL) | Assessment |
|------|-----------------|------------|
| 2012-10-24 | 85.77 | Normal |
| 2014-10-29 | 72.17 | Normal |
| 2016-11-02 | 71.06 | Normal |
| 2018-10-10 | 78.54 | Normal |
| 2019-10-16 | 91.87 | Normal |
| 2020-10-21 | 90.96 | Normal |

> **Key finding:** Glucose levels remain controlled (on Metformin), all within normal range.

#### HbA1c Trend (LOINC: 4548-4)
| Date | HbA1c (%) | Assessment |
|------|-----------|------------|
| 2012-10-24 | 5.69 | Normal |
| 2014-10-29 | 5.84 | Normal |
| 2016-11-02 | **6.13** | Pre-diabetic range |
| 2018-10-10 | 5.44 | Normal |
| 2019-10-16 | 5.44 | Normal |
| 2020-10-21 | 5.44 | Normal |

> **Key finding:** HbA1c spiked to 6.13% in 2016 but came back under control. Generally well-managed on Metformin.

#### BMI Trend (LOINC: 39156-5)
| Date | BMI (kg/m2) | Weight (kg) | Assessment |
|------|-------------|-------------|------------|
| 2012-10-24 | 28.76 | 73.25 | Overweight |
| 2014-10-29 | 29.36 | 74.80 | Overweight |
| 2016-11-02 | **30.54** | **77.79** | Obese Class I |
| 2018-10-10 | 27.77 | 70.73 | Overweight |
| 2019-10-16 | 27.77 | 70.73 | Overweight |
| 2020-10-21 | 27.77 | 70.73 | Overweight |

#### Full Observation List (148 total)
| Date | Observation | LOINC | Value |
|------|-------------|-------|-------|
| 2020-10-21 | Hematocrit | 4544-3 | 43.19% |
| 2020-10-21 | Hemoglobin | 718-7 | 13.42 g/dL |
| 2020-10-21 | Erythrocytes | 789-8 | 4.35 10*6/uL |
| 2020-10-21 | Leukocytes | 6690-2 | 6.08 10*3/uL |
| 2020-10-21 | Microalbumin/Creatinine Ratio | 14959-1 | 10.13 mg/g |
| 2020-10-21 | Smoking Status | 72166-2 | Never smoker |
| 2020-10-21 | Body Weight | 29463-7 | 70.73 kg |
| 2020-10-21 | CO2 | 20565-8 | 23.10 mmol/L |
| 2020-10-21 | RDW | 21000-5 | 39.24 fL |
| 2020-10-21 | Body Height | 8302-2 | 159.60 cm |
| 2020-10-21 | Sodium | 2947-0 | 140.26 mmol/L |
| 2020-10-21 | Triglycerides | 2571-8 | 113.24 mg/dL |
| 2020-10-21 | Creatinine | 38483-4 | 0.80 mg/dL |
| 2020-10-21 | Blood Pressure | 55284-4 | 163.2/110.6 mm[Hg] |
| 2020-10-21 | HDL | 2085-9 | 78.71 mg/dL |
| 2020-10-21 | eGFR | 33914-3 | 92.36 mL/min |
| 2020-10-21 | Chloride | 2069-3 | 106.60 mmol/L |
| 2020-10-21 | BUN | 6299-2 | 15.91 mg/dL |
| 2020-10-21 | BMI | 39156-5 | 27.77 kg/m2 |
| 2020-10-21 | Platelet Mean Volume | 32623-1 | 9.97 fL |
| 2020-10-21 | PDW | 32207-3 | 376.71 fL |
| 2020-10-21 | Platelets | 777-3 | 249.03 10*3/uL |
| 2020-10-21 | MCHC | 786-4 | 35.61 g/dL |
| 2020-10-21 | MCH | 785-6 | 28.02 pg |
| 2020-10-21 | MCV | 787-2 | 89.41 fL |
| 2020-10-21 | LDL | 18262-6 | 59.22 mg/dL |
| 2020-10-21 | Glucose | 2339-0 | 90.96 mg/dL |
| 2020-10-21 | Calcium | 49765-1 | 8.64 mg/dL |
| 2020-10-21 | Potassium | 6298-4 | 4.16 mmol/L |
| 2020-10-21 | Total Cholesterol | 2093-3 | 160.58 mg/dL |
| 2020-10-21 | HbA1c | 4548-4 | 5.44% |
| 2020-10-21 | Pain Score | 72514-3 | 1.99 |
| 2019-10-16 | CO2 | 20565-8 | 23.12 mmol/L |
| 2019-10-16 | Chloride | 2069-3 | 101.50 mmol/L |
| 2019-10-16 | Potassium | 6298-4 | 4.99 mmol/L |
| 2019-10-16 | Creatinine | 38483-4 | 0.75 mg/dL |
| 2019-10-16 | BMI | 39156-5 | 27.77 kg/m2 |
| 2019-10-16 | Sodium | 2947-0 | 143.02 mmol/L |
| 2019-10-16 | eGFR | 33914-3 | 101.75 mL/min |
| 2019-10-16 | Calcium | 49765-1 | 9.90 mg/dL |
| 2019-10-16 | Total Cholesterol | 2093-3 | 182.57 mg/dL |
| 2019-10-16 | HbA1c | 4548-4 | 5.44% |
| 2019-10-16 | Triglycerides | 2571-8 | 128.29 mg/dL |
| 2019-10-16 | LDL | 18262-6 | 78.40 mg/dL |
| 2019-10-16 | HDL | 2085-9 | 78.52 mg/dL |
| 2019-10-16 | Body Height | 8302-2 | 159.60 cm |
| 2019-10-16 | Glucose | 2339-0 | 91.87 mg/dL |
| 2019-10-16 | Pain Score | 72514-3 | 2.04 |
| 2019-10-16 | Blood Pressure | 55284-4 | 170.3/97.6 mm[Hg] |
| 2019-10-16 | Body Weight | 29463-7 | 70.73 kg |
| 2019-10-16 | Smoking Status | 72166-2 | Never smoker |
| 2019-10-16 | BUN | 6299-2 | 11.43 mg/dL |
| 2019-10-16 | Microalbumin/Creatinine Ratio | 14959-1 | 10.52 mg/g |
| 2018-10-10 | CO2 | 20565-8 | 23.34 mmol/L |
| 2018-10-10 | Pain Score | 72514-3 | 0.08 |
| 2018-10-10 | Blood Pressure | 55284-4 | 140.2/100.2 mm[Hg] |
| 2018-10-10 | HbA1c | 4548-4 | 5.44% |
| 2018-10-10 | Creatinine | 38483-4 | 0.77 mg/dL |
| 2018-10-10 | Total Cholesterol | 2093-3 | 160.75 mg/dL |
| 2018-10-10 | Microalbumin/Creatinine Ratio | 14959-1 | 6.10 mg/g |
| 2018-10-10 | LDL | 18262-6 | 63.69 mg/dL |
| 2018-10-10 | Triglycerides | 2571-8 | 129.37 mg/dL |
| 2018-10-10 | eGFR | 33914-3 | 99.27 mL/min |
| 2018-10-10 | Chloride | 2069-3 | 104.45 mmol/L |
| 2018-10-10 | Body Height | 8302-2 | 159.60 cm |
| 2018-10-10 | Glucose | 2339-0 | 78.54 mg/dL |
| 2018-10-10 | HDL | 2085-9 | 71.18 mg/dL |
| 2018-10-10 | Body Weight | 29463-7 | 70.73 kg |
| 2018-10-10 | Sodium | 2947-0 | 139.72 mmol/L |
| 2018-10-10 | Calcium | 49765-1 | 8.61 mg/dL |
| 2018-10-10 | Potassium | 6298-4 | 3.96 mmol/L |
| 2018-10-10 | Smoking Status | 72166-2 | Never smoker |
| 2018-10-10 | BUN | 6299-2 | 10.17 mg/dL |
| 2018-10-10 | BMI | 39156-5 | 27.77 kg/m2 |
| 2016-11-02 | BUN | 6299-2 | 7.76 mg/dL |
| 2016-11-02 | eGFR | 33914-3 | 152.47 mL/min |
| 2016-11-02 | Total Cholesterol | 2093-3 | 173.85 mg/dL |
| 2016-11-02 | Sodium | 2947-0 | 137.99 mmol/L |
| 2016-11-02 | CO2 | 20565-8 | 20.71 mmol/L |
| 2016-11-02 | Calcium | 49765-1 | 8.68 mg/dL |
| 2016-11-02 | Blood Pressure | 55284-4 | 148.0/103.7 mm[Hg] |
| 2016-11-02 | HDL | 2085-9 | 64.20 mg/dL |
| 2016-11-02 | Glucose | 2339-0 | 71.06 mg/dL |
| 2016-11-02 | BMI | 39156-5 | 30.54 kg/m2 |
| 2016-11-02 | Microalbumin/Creatinine Ratio | 14959-1 | 13.29 mg/g |
| 2016-11-02 | Body Weight | 29463-7 | 77.79 kg |
| 2016-11-02 | Chloride | 2069-3 | 102.35 mmol/L |
| 2016-11-02 | Triglycerides | 2571-8 | 128.50 mg/dL |
| 2016-11-02 | Smoking Status | 72166-2 | Never smoker |
| 2016-11-02 | HbA1c | 4548-4 | 6.13% |
| 2016-11-02 | Body Height | 8302-2 | 159.60 cm |
| 2016-11-02 | LDL | 18262-6 | 83.95 mg/dL |
| 2016-11-02 | Pain Score | 72514-3 | 3.04 |
| 2016-11-02 | Creatinine | 38483-4 | 0.84 mg/dL |
| 2016-11-02 | Potassium | 6298-4 | 5.17 mmol/L |
| 2014-10-29 | Hemoglobin | 718-7 | 16.46 g/dL |
| 2014-10-29 | BMI | 39156-5 | 29.36 kg/m2 |
| 2014-10-29 | BUN | 6299-2 | 19.57 mg/dL |
| 2014-10-29 | RDW | 21000-5 | 43.07 fL |
| 2014-10-29 | Creatinine | 38483-4 | 1.09 mg/dL |
| 2014-10-29 | Potassium | 6298-4 | 3.84 mmol/L |
| 2014-10-29 | Chloride | 2069-3 | 110.26 mmol/L |
| 2014-10-29 | Erythrocytes | 789-8 | 4.67 10*6/uL |
| 2014-10-29 | Hematocrit | 4544-3 | 44.10% |
| 2014-10-29 | Calcium | 49765-1 | 9.01 mg/dL |
| 2014-10-29 | MCV | 787-2 | 92.34 fL |
| 2014-10-29 | Microalbumin/Creatinine Ratio | 14959-1 | 2.45 mg/g |
| 2014-10-29 | MCHC | 786-4 | 33.91 g/dL |
| 2014-10-29 | Body Weight | 29463-7 | 74.80 kg |
| 2014-10-29 | LDL | 18262-6 | 70.85 mg/dL |
| 2014-10-29 | HDL | 2085-9 | 78.18 mg/dL |
| 2014-10-29 | Platelets | 777-3 | 339.90 10*3/uL |
| 2014-10-29 | PDW | 32207-3 | 329.03 fL |
| 2014-10-29 | Triglycerides | 2571-8 | 136.05 mg/dL |
| 2014-10-29 | Pain Score | 72514-3 | 0.02 |
| 2014-10-29 | Total Cholesterol | 2093-3 | 176.24 mg/dL |
| 2014-10-29 | Blood Pressure | 55284-4 | 167.0/117.3 mm[Hg] |
| 2014-10-29 | Smoking Status | 72166-2 | Never smoker |
| 2014-10-29 | HbA1c | 4548-4 | 5.84% |
| 2014-10-29 | eGFR | 33914-3 | 76.28 mL/min |
| 2014-10-29 | Leukocytes | 6690-2 | 9.48 10*3/uL |
| 2014-10-29 | Platelet Mean Volume | 32623-1 | 11.62 fL |
| 2014-10-29 | MCH | 785-6 | 28.25 pg |
| 2014-10-29 | Sodium | 2947-0 | 139.65 mmol/L |
| 2014-10-29 | Glucose | 2339-0 | 72.17 mg/dL |
| 2014-10-29 | Body Height | 8302-2 | 159.60 cm |
| 2014-10-29 | CO2 | 20565-8 | 25.99 mmol/L |
| 2012-10-24 | BUN | 6299-2 | 16.78 mg/dL |
| 2012-10-24 | Chloride | 2069-3 | 105.13 mmol/L |
| 2012-10-24 | Creatinine | 38483-4 | 0.85 mg/dL |
| 2012-10-24 | CO2 | 20565-8 | 22.32 mmol/L |
| 2012-10-24 | Calcium | 49765-1 | 9.25 mg/dL |
| 2012-10-24 | Sodium | 2947-0 | 136.28 mmol/L |
| 2012-10-24 | Microalbumin/Creatinine Ratio | 14959-1 | 13.46 mg/g |
| 2012-10-24 | Potassium | 6298-4 | 4.58 mmol/L |
| 2012-10-24 | Body Height | 8302-2 | 159.60 cm |
| 2012-10-24 | HbA1c | 4548-4 | 5.69% |
| 2012-10-24 | Body Weight | 29463-7 | 73.25 kg |
| 2012-10-24 | Blood Pressure | 55284-4 | 160.5/105.8 mm[Hg] |
| 2012-10-24 | Total Cholesterol | 2093-3 | 174.96 mg/dL |
| 2012-10-24 | Triglycerides | 2571-8 | 119.51 mg/dL |
| 2012-10-24 | LDL | 18262-6 | 79.17 mg/dL |
| 2012-10-24 | HDL | 2085-9 | 71.89 mg/dL |
| 2012-10-24 | eGFR | 33914-3 | 98.40 mL/min |
| 2012-10-24 | Smoking Status | 72166-2 | Never smoker |
| 2012-10-24 | Pain Score | 72514-3 | 1.46 |
| 2012-10-24 | Glucose | 2339-0 | 85.77 mg/dL |
| 2012-10-24 | BMI | 39156-5 | 28.76 kg/m2 |

---

### Encounters (42 total)

| Resource ID | Date | Class | Type | SNOMED |
|-------------|------|-------|------|--------|
| `66ebe424-eb61-40ea-82e1-9ccc45f7371f` | 2020-10-21 | AMB | Encounter for check up | 185349003 |
| `fe4889eb-9a1e-4e9b-aa40-63f76e235573` | 2020-07-04 | AMB | Encounter for symptom | 185345009 |
| `3d8892b6-2f81-4247-933b-1b68ab7624ef` | 2019-10-16 | AMB | Encounter for check up | 185349003 |
| `6aba879d-eb2b-4b6f-8b54-b0a668f4f4af` | 2019-09-04 | AMB | Postnatal visit | 169762003 |
| `ac1b3f76-e5a2-42cd-8901-918172c7b74a` | 2019-07-24 | **EMER** | **Obstetric emergency** | 183460006 |
| `25c7ef60-8048-4644-afb8-f0dc3633c5e1` | 2019-07-17 | AMB | Prenatal visit | 424619006 |
| `b5e5d775-e4aa-415e-bb3e-ad27239cf873` | 2019-07-10 | AMB | Prenatal visit | 424619006 |
| `39044dcd-3c27-4e9f-9e41-503ce03de4c9` | 2019-06-26 | AMB | Prenatal visit | 424619006 |
| `5b4311b1-a7ea-4ce2-b59e-73f54a849dcf` | 2019-05-29 | AMB | Prenatal visit | 424619006 |
| `2e98eef9-6912-470f-9eec-4f10800bb96b` | 2019-05-01 | AMB | Prenatal visit | 424619006 |
| `7536a047-947d-4f44-8dd4-9fd86356d679` | 2019-04-03 | AMB | Prenatal visit | 424619006 |
| `dd666aec-96a1-45c1-89c8-3c3bee31de8f` | 2019-03-06 | AMB | Prenatal visit | 424619006 |
| `6c9faf83-c08d-4ae6-b75d-e990a8c466aa` | 2019-02-06 | AMB | Prenatal visit | 424619006 |
| `c2d9dc47-9590-40c6-b1ba-d2498717db84` | 2019-01-09 | AMB | Prenatal visit | 424619006 |
| `96a77913-e2dc-4869-af89-57699e2f2cde` | 2018-12-12 | AMB | Prenatal initial visit | 424441002 |
| `458e523d-6be4-407e-a071-f759f9a8efa6` | 2018-10-10 | AMB | Encounter for check up | 185349003 |
| `2d3db836-a476-421a-b39a-f1b1f0db86d5` | 2018-10-10 | AMB | Encounter for check-up | 185349003 |
| `9671992a-f036-42b2-8fd7-96ec3d5ebee1` | 2018-09-05 | AMB | Prenatal visit | 424619006 |
| `5d0035c8-4528-496d-9a0d-54f003c99e60` | 2018-08-29 | AMB | Prenatal initial visit | 424441002 |
| `fccc3408-7aed-4276-bbdb-51f4c3751946` | 2017-07-29 | AMB | Encounter for symptom | 185345009 |
| `2b26de91-5b79-45a6-b055-63d9b2b33f0f` | 2016-11-02 | AMB | Encounter for check up | 185349003 |
| `de437239-9e62-4559-a036-5324c8868993` | 2016-08-17 | AMB | Consultation for treatment | 698314001 |
| `16fdfd62-584c-4bf4-9ac8-de9d7efc3d4a` | 2016-08-17 | AMB | Prenatal visit | 424619006 |
| `9d83a66b-ca05-4a38-bb5d-706d6c32a8e0` | 2016-08-10 | AMB | Prenatal initial visit | 424441002 |
| `66f46f9a-e7e2-4677-8c61-72760c57ab43` | 2016-01-13 | AMB | Prenatal visit | 424619006 |
| `f06e5198-e7d3-4229-bf67-dff7abbf5fcd` | 2015-12-30 | AMB | Patient-initiated encounter | 270427003 |
| `6b684b52-6188-42ad-aa34-be55656a20c8` | 2015-12-23 | AMB | Prenatal initial visit | 424441002 |
| `1d4d1be5-75df-49ef-ae85-a4a63f826af0` | 2015-02-19 | AMB | Encounter for check-up | 185349003 |
| `0e34faef-fe97-4298-8758-aaa1b049077a` | 2015-01-20 | **EMER** | **Emergency room admission** | 50849002 |
| `ca1e0dae-943e-4f93-87e5-62fa8106243f` | 2014-10-29 | AMB | Encounter for check up | 185349003 |
| `07e63933-aaf2-4c79-9fc2-5f86a0700bb0` | 2014-10-29 | AMB | Prenatal visit | 424619006 |
| `3ab234a5-0e74-4ff3-a259-4949230605e2` | 2014-10-22 | AMB | Prenatal initial visit | 424441002 |
| `b41056a4-9bd6-4815-bf8e-e6504c556e43` | 2013-10-09 | AMB | Prenatal visit | 424619006 |
| `cbea2ebf-f67b-41e4-aa47-b27d7a4fafda` | 2013-09-25 | AMB | Prenatal initial visit | 424441002 |
| `c578f890-21a6-498c-aaee-8667e35c5ad9` | 2013-07-24 | AMB | Patient encounter procedure | 308335008 |
| `b0d5adc6-6383-4cd2-ba36-1aafccdc5eb0` | 2012-10-24 | AMB | Encounter for check up | 185349003 |
| `e50ab2f8-cc4e-45fe-98a0-9a2bed1ec0b3` | 2012-07-29 | AMB | Consultation for treatment | 698314001 |
| `dc52509e-184d-4739-8abf-31c213956766` | 2010-10-20 | AMB | Encounter for check up | 185349003 |
| `e6e5b94c-b335-428e-88fb-a31a8e77dc0c` | 2010-08-09 | AMB | Consultation for treatment | 698314001 |
| `f1022603-02e0-4daf-bfe7-6ac789614b6c` | 2008-10-15 | AMB | Encounter for check up | 185349003 |
| `e88be355-be32-48ff-a170-19bf1a3b7132` | 2006-01-18 | AMB | Encounter for check up | 185349003 |
| `942c89e4-7046-40cd-9f36-5ae8e314e171` | 2003-01-15 | AMB | Encounter for check up | 185349003 |

---

### Immunizations (9 total)

| Resource ID | Vaccine | CVX Code | Date |
|-------------|---------|----------|------|
| `1e3bab7a-92c3-41cb-87bb-89adfa80a5e0` | Influenza (preservative free) | 140 | 2012-10-24 |
| `57dcc56a-4f3a-4157-9922-460ac80ffa64` | Influenza (preservative free) | 140 | 2014-10-29 |
| `96422f7a-15e7-4a17-a967-237131295b11` | Influenza (preservative free) | 140 | 2016-11-02 |
| `c281de50-6e69-420e-85cb-a55a90b49b08` | Zoster | 121 | 2018-10-10 |
| `79930be5-807a-4335-beac-8758e9633eb7` | Influenza (preservative free) | 140 | 2018-10-10 |
| `dc63d567-ed6c-4a3c-a3ac-2f627c875643` | Zoster | 121 | 2019-10-16 |
| `672b7838-99d6-4b34-aa77-162c55741054` | Td (adult, preservative free) | 113 | 2019-10-16 |
| `5911fb34-154b-4227-96bc-16ca4e220204` | Influenza (preservative free) | 140 | 2019-10-16 |
| `766a0fbe-967a-4eb6-85f8-c976818abb6e` | Influenza (preservative free) | 140 | 2020-10-21 |

---

### Care Plans (3 total)

| Resource ID | Category | SNOMED | Status | Period |
|-------------|----------|--------|--------|--------|
| `a1137ae0-3235-435b-9940-9616f913caa0` | **Diabetes self management** | 698360004 | **active** | 2003-01-15 - ongoing |
| `8205d31a-8101-4328-a234-446dd7e53a77` | Fracture care | 385691007 | completed | 2015-01-20 to 2015-02-19 |
| `d0461449-a0e3-4ee4-b212-98ee63c0f050` | **Routine antenatal care** | 134435003 | completed | 2018-12-12 to 2019-07-24 |

**Active Diabetes Care Plan Activities:**
- Diabetic diet (SNOMED: 160670007) - in-progress
- Exercise therapy (SNOMED: 229065009) - in-progress

**Completed Antenatal Care Activities:**
- Antenatal education (SNOMED: 135892000)
- Antenatal risk assessment (SNOMED: 713076009)
- Antenatal blood tests (SNOMED: 312404004)

---

### Goals (5 total)

| Resource ID | Description | Status |
|-------------|-------------|--------|
| `b90493f4-7ea8-4aaa-903a-e27edee13557` | **HbA1c < 7.0%** | in-progress |
| `d2f0c78b-7fd6-49e7-a01c-3ba39d28ec42` | **Glucose < 108 mg/dL** | in-progress |
| `dc5d7f64-ff98-400e-8651-7d265503d049` | **BP below 140/90 mmHg** | in-progress |
| `ea65b6af-5c04-453a-81a8-c5c407cf9ef9` | Foot health / prevent neuropathy ulcers | in-progress |
| `6a889a5c-333b-4192-9fc5-05d05bbaf092` | Diabetic self-care knowledge | in-progress |

---

## 2. CHRONOLOGICAL CLINICAL TIMELINE

### 2003 - Dual Diagnosis Year
- **2003-01-15** | Checkup encounter (`942c89e4`)
  - **Diagnosed: Diabetes (Type 2)** (SNOMED: 44054006)
  - **Diagnosed: Hypertension** (SNOMED: 38341003)
  - **Started: Hydrochlorothiazide 25 MG** for hypertension (still active)
  - **Care Plan initiated:** Diabetes self management (still active)
  - **Goals set:** HbA1c < 7%, Glucose < 108, BP < 140/90

### 2006 - Metabolic Complications
- **2006-01-18** | Checkup encounter (`e88be355`)
  - **Diagnosed: Metabolic syndrome X** (SNOMED: 237602007)
  - **Diagnosed: Hypertriglyceridemia** (SNOMED: 302870006)
  - **Diagnosed: Anemia** (SNOMED: 271737000)
  - **Started: Metformin ER 500 MG** for diabetes (still active)

### 2008 - Hyperglycemia
- **2008-10-15** | Checkup encounter (`f1022603`)
  - **Diagnosed: Hyperglycemia** (SNOMED: 80394007)

### 2010 - Neuropathy and Contraception
- **2010-08-09** | Consultation (`e6e5b94c`)
  - **Started: Camila (norethindrone)** contraceptive
- **2010-10-20** | Checkup encounter (`dc52509e`)
  - **Diagnosed: Prediabetes** (SNOMED: 15777000)
  - **Diagnosed: Diabetic neuropathy** (SNOMED: 368581000119106)

### 2012 - Contraceptive Change
- **2012-07-29** | Consultation (`e50ab2f8`)
  - Stopped Camila; **Started: Jolivette** (norethindrone)
- **2012-10-24** | Checkup + Labs
  - BP: 160/106 (uncontrolled), HbA1c: 5.69%, Glucose: 85.8
  - BMI: 28.76 (overweight), Flu vaccine

### 2013 - Pregnancy #1 (MISCARRIAGE)
- **2013-07-24** | Patient encounter (`c578f890`)
- **2013-09-25** | Prenatal initial visit (`cbea2ebf`)
  - **Pregnancy #1 begins** (SNOMED: 72892002)
  - **Complication: Blighted ovum** (SNOMED: 35999006)
- **2013-10-09** | Prenatal visit (`b41056a4`)
  - **MISCARRIAGE in first trimester** (SNOMED: 19169002)
  - Pregnancy and blighted ovum resolved

### 2014 - Pregnancy #2 (FETAL COMPLICATION / LOSS)
- **2014-10-22** | Prenatal initial visit (`3ab234a5`)
  - **Pregnancy #2 begins** (SNOMED: 72892002)
  - **Complication: Fetus with unknown complication** (SNOMED: 156073000)
- **2014-10-29** | Prenatal visit + Checkup + Labs
  - Pregnancy resolved (1 week - early loss)
  - BP: 167/117 (severely elevated), HbA1c: 5.84%
  - BMI: 29.36, Weight: 74.8 kg

### 2015 - Ankle Fracture (ED Visit)
- **2015-01-20** | **EMERGENCY ROOM** (`0e34faef`)
  - **Fracture of ankle** (SNOMED: 16114001)
  - Prescribed: Meperidine 50 MG (q4h) + Naproxen 220 MG (PRN)
  - Care Plan: Fracture care (rest + light exercise)
- **2015-02-19** | Follow-up checkup
  - Fracture resolved, care plan completed

### 2015-2016 - Pregnancy #3 (EARLY LOSS)
- **2015-12-23** | Prenatal initial visit (`6b684b52`)
  - **Pregnancy #3 begins**
- **2015-12-30** | Patient-initiated visit
- **2016-01-13** | Prenatal visit (`66f46f9a`)
  - Pregnancy resolved (3 weeks - early loss)

### 2016 - Pregnancy #4 (BLIGHTED OVUM)
- **2016-08-10** | Prenatal initial visit (`9d83a66b`)
  - **Pregnancy #4 begins**
  - **Complication: Blighted ovum** (SNOMED: 35999006)
- **2016-08-17** | Prenatal visit + Consultation
  - Pregnancy resolved (1 week - blighted ovum)
  - **Restarted: Camila (norethindrone)** contraceptive
- **2016-11-02** | Checkup + Labs
  - BP: 148/104, **HbA1c: 6.13%** (worst reading)
  - **BMI: 30.54** (crossed into obesity), Weight: 77.8 kg

### 2017 - Sinusitis
- **2017-07-29** | Symptom encounter (`fccc3408`)
  - **Viral sinusitis** (resolved 2017-08-12)

### 2018 - Pregnancy #5 (FETAL COMPLICATION) then Pregnancy #6 (SUCCESS)
- **2018-08-29** | Prenatal initial visit (`5d0035c8`)
  - **Pregnancy #5 begins**
  - **Complication: Fetus with unknown complication**
- **2018-09-05** | Prenatal visit (`9671992a`)
  - Pregnancy #5 resolved (1 week - early loss)
- **2018-10-10** | Checkup + Labs
  - BP: 140/100, HbA1c: 5.44%, Glucose: 78.5
  - BMI: 27.77 (weight dropped from 77.8 to 70.7 kg)
  - Zoster + Flu vaccines
- **2018-12-12** | **Prenatal initial visit** (`96a77913`)
  - **PREGNANCY #6 BEGINS** -- this one succeeds!
  - **Antenatal care plan initiated** (education, risk assessment, blood tests)
  - Stopped Camila contraceptive

### 2019 - Successful Pregnancy and Delivery
- **2019-01-09** | Prenatal visit
- **2019-02-06** | Prenatal visit
- **2019-03-06** | Prenatal visit
- **2019-04-03** | Prenatal visit
- **2019-05-01** | Prenatal visit
- **2019-05-29** | Prenatal visit
- **2019-06-26** | Prenatal visit
- **2019-07-10** | Prenatal visit
- **2019-07-17** | Prenatal visit (last regular)
- **2019-07-24** | **OBSTETRIC EMERGENCY** (`ac1b3f76`) -- Class: EMER
  - **DELIVERY** -- Pregnancy resolved
  - Antenatal care plan completed
- **2019-09-04** | **Postnatal visit** (`6aba879d`)
- **2019-10-16** | Checkup + Labs
  - BP: 170/98 (spiked postpartum), HbA1c: 5.44%
  - Td, Zoster, Flu vaccines

### 2020 - Ongoing Chronic Management
- **2020-07-04** | Symptom encounter -- Viral sinusitis (resolved 2020-07-11)
- **2020-10-21** | Checkup + Labs (most recent)
  - BP: 163/111 (still uncontrolled)
  - HbA1c: 5.44%, Glucose: 91.0
  - BMI: 27.77, Weight: 70.7 kg
  - Flu vaccine

---

## 3. RISK PROFILE SUMMARY

**Maria's Key Risk Factors:**
1. **Poorly controlled hypertension** -- BP never below 140/90, consistently Stage 2
2. **Type 2 diabetes with neuropathy** -- on Metformin, HbA1c well-controlled (<6%)
3. **Metabolic syndrome** (hypertriglyceridemia, obesity history)
4. **Extensive obstetric loss history** -- 5 pregnancy losses before 1 successful delivery
   - 1 miscarriage (1st trimester)
   - 2 blighted ova
   - 2 fetal complications (unknown)
   - 1 early loss (3 weeks)
5. **Obstetric emergency delivery** at age 50
6. **Anemia** (chronic)
7. **Race/age risk** -- Black woman, advanced maternal age (50 at delivery)

---

## 4. ALTERNATIVE PREGNANT PATIENTS FOR DEMO

### Patient A: Kimiko Dooley (LOW RISK)
| Field | Value |
|-------|-------|
| **Patient ID** | `75e95f92-3bfa-454f-aa99-99375173f201` |
| **DOB** | 1996-11-07 (age ~29) |
| **Total Conditions** | 5 |
| **Risk Profile** | **LOW** -- Young, only chronic sinusitis. 1 prior normal pregnancy (2017). Currently pregnant (2020, active). |
| **Conditions** | Chronic sinusitis (40055000), Concussion resolved (62106007), Viral sinusitis resolved (444814009), Normal pregnancy 2017 resolved, Normal pregnancy 2020 active |

### Patient B: Misty Bradtke (VERY HIGH RISK)
| Field | Value |
|-------|-------|
| **Patient ID** | `45ecc2b1-2e0c-4e67-bdac-2979f439275a` |
| **DOB** | 1973-05-14 (age ~52) |
| **Total Conditions** | 15 |
| **Risk Profile** | **VERY HIGH** -- Prediabetes, hypertension, anemia, prior preeclampsia, tubal pregnancy, miscarriage, blighted ovum, recurrent UTI, STROKE. |
| **Key Conditions** | Hypertension (38341003), Prediabetes (15777000), Anemia (271737000), Stroke (230690007), Preeclampsia (398254007), Tubal pregnancy (79586000), Miscarriage (19169002), Recurrent UTI (197927001) |
| **Pregnancies** | 5 total -- multiple complications including preeclampsia and tubal |

### Patient C: Meg Toy (MODERATE-HIGH RISK)
| Field | Value |
|-------|-------|
| **Patient ID** | `138d4e0c-e3d3-460d-bead-7d0b2f86f33c` |
| **DOB** | 1984-04-10 (age ~41) |
| **Total Conditions** | 14 |
| **Risk Profile** | **MODERATE-HIGH** -- Hypertension, prior preeclampsia, chronic pain, chronic migraine, drug overdose history. |
| **Key Conditions** | Hypertension (38341003), Preeclampsia (398254007), Chronic pain (82423001), Chronic migraine (124171000119105), Drug overdose (55680006) |
| **Pregnancies** | 4 total -- 1 complicated by preeclampsia (2013) |

---

## 5. FHIR RESOURCE ID QUICK REFERENCE

### Critical Resource IDs for Maria
```
Patient:           881f534f-d041-425d-a542-cbf669f43e18
Diabetes:          abc9ea4f-6eb2-44b6-8f02-e16cb056b5ca
Hypertension:      07c4fa62-b6c4-44c0-9443-6f6e59dc47cb
Diabetic Neuro:    70758a4d-cacc-4206-9621-571dd6de6528
Pregnancy (last):  9f80e77a-1580-480f-a4e5-48ec05ca4354
Miscarriage:       c38df46a-5d39-4920-9664-38c9044454c4
Metformin (active):f6255a19-d66f-41df-a70f-42a68ae2b36f
HCTZ (active):     91a9e5d7-4e57-4879-9340-611acb049f8f
Diabetes CarePlan: a1137ae0-3235-435b-9940-9616f913caa0
Antenatal CarePlan:d0461449-a0e3-4ee4-b212-98ee63c0f050
OB Emergency Enc:  ac1b3f76-e5a2-42cd-8901-918172c7b74a
ED Fracture Enc:   0e34faef-fe97-4298-8758-aaa1b049077a
HbA1c Goal:        b90493f4-7ea8-4aaa-903a-e27edee13557
BP Goal:           dc5d7f64-ff98-400e-8651-7d265503d049
Glucose Goal:      d2f0c78b-7fd6-49e7-a01c-3ba39d28ec42
```

### FHIR Query Templates
```bash
# Base URL
BASE="https://r4.smarthealthit.org"
PID="881f534f-d041-425d-a542-cbf669f43e18"

# Patient
curl "$BASE/Patient/$PID?_format=json"

# All conditions
curl "$BASE/Condition?patient=$PID&_count=100&_format=json"

# Recent observations
curl "$BASE/Observation?patient=$PID&_count=200&_sort=-date&_format=json"

# Medications
curl "$BASE/MedicationRequest?patient=$PID&_count=50&_format=json"

# Encounters
curl "$BASE/Encounter?patient=$PID&_count=100&_sort=-date&_format=json"

# Specific observation by LOINC code (e.g., HbA1c)
curl "$BASE/Observation?patient=$PID&code=http://loinc.org|4548-4&_sort=-date&_format=json"

# Specific condition by SNOMED (e.g., pregnancy)
curl "$BASE/Condition?patient=$PID&code=http://snomed.info/sct|72892002&_format=json"
```

---

## 6. KEY LOINC AND SNOMED CODES USED

### LOINC Codes (Observations)
| Code | Name | Category |
|------|------|----------|
| 55284-4 | Blood Pressure | Vital Signs |
| 2339-0 | Glucose | Lab |
| 4548-4 | HbA1c | Lab |
| 39156-5 | BMI | Vital Signs |
| 29463-7 | Body Weight | Vital Signs |
| 8302-2 | Body Height | Vital Signs |
| 2093-3 | Total Cholesterol | Lab |
| 2571-8 | Triglycerides | Lab |
| 18262-6 | LDL Cholesterol | Lab |
| 2085-9 | HDL Cholesterol | Lab |
| 38483-4 | Creatinine | Lab |
| 33914-3 | eGFR | Lab |
| 14959-1 | Microalbumin/Creatinine Ratio | Lab |
| 72166-2 | Smoking Status | Social History |
| 718-7 | Hemoglobin | Lab |
| 4544-3 | Hematocrit | Lab |
| 789-8 | Erythrocytes | Lab |
| 6690-2 | Leukocytes | Lab |
| 777-3 | Platelets | Lab |
| 786-4 | MCHC | Lab |
| 785-6 | MCH | Lab |
| 787-2 | MCV | Lab |
| 21000-5 | RDW | Lab |
| 32623-1 | Platelet Mean Volume | Lab |
| 32207-3 | Platelet Distribution Width | Lab |
| 2947-0 | Sodium | Lab |
| 2069-3 | Chloride | Lab |
| 6298-4 | Potassium | Lab |
| 49765-1 | Calcium | Lab |
| 20565-8 | Carbon Dioxide | Lab |
| 6299-2 | BUN | Lab |
| 72514-3 | Pain Score | Assessment |

### SNOMED Codes (Conditions)
| Code | Display |
|------|---------|
| 44054006 | Diabetes mellitus type 2 |
| 38341003 | Hypertension |
| 237602007 | Metabolic syndrome X |
| 302870006 | Hypertriglyceridemia |
| 271737000 | Anemia |
| 80394007 | Hyperglycemia |
| 15777000 | Prediabetes |
| 368581000119106 | Diabetic neuropathy (type 2) |
| 72892002 | Normal pregnancy |
| 35999006 | Blighted ovum |
| 19169002 | Miscarriage in first trimester |
| 156073000 | Fetus with unknown complication |
| 16114001 | Fracture of ankle |
| 444814009 | Viral sinusitis |

### SNOMED Codes (Encounters)
| Code | Display |
|------|---------|
| 185349003 | Encounter for check up |
| 424441002 | Prenatal initial visit |
| 424619006 | Prenatal visit |
| 169762003 | Postnatal visit |
| 183460006 | Obstetric emergency hospital admission |
| 50849002 | Emergency room admission |
| 698314001 | Consultation for treatment |
| 185345009 | Encounter for symptom |
| 270427003 | Patient-initiated encounter |
| 308335008 | Patient encounter procedure |

### SNOMED Codes (Care Plans / Activities)
| Code | Display |
|------|---------|
| 698360004 | Diabetes self management plan |
| 385691007 | Fracture care |
| 134435003 | Routine antenatal care |
| 160670007 | Diabetic diet |
| 229065009 | Exercise therapy |
| 183051005 | Recommendation to rest |
| 408580007 | Physical activity target light exercise |
| 135892000 | Antenatal education |
| 713076009 | Antenatal risk assessment |
| 312404004 | Antenatal blood tests |

### CVX Codes (Immunizations)
| Code | Display |
|------|---------|
| 140 | Influenza, seasonal, injectable, preservative free |
| 121 | Zoster |
| 113 | Td (adult) preservative free |
