# Duchenne Access Coverage Toolkit

This repository contains data and code to build a spatial access toolkit for Duchenne muscular dystrophy (DMD) care in the United States.  The goal is to identify where certified Duchenne care centers are located, estimate how many potential DMD patients live in each county, calculate distance‐ and time‐based coverage metrics, and highlight gaps in access to care.

## Directory structure

```
duchenne_toolkit/
├── data_raw/            # Raw inputs downloaded from external sources
├── data_intermediate/   # Intermediate processed data
├── data_final/          # Final analysis outputs (CSV files)
├── notebooks/           # Jupyter notebooks for exploratory work
├── src/                 # Python source code
├── maps/                # Interactive and static map outputs
├── docs/                # Documentation, reports and citations
├── requirements.txt     # Python package requirements
├── environment.yml      # Conda environment specification
├── Makefile             # Task runner for reproducible pipeline
└── LICENSE              # Licensing information
```

## Quick start

The pipeline requires Python 3.11 with [conda](https://docs.conda.io/) or [virtualenv](https://virtualenv.pypa.io/) installed.  To reproduce the analysis on a clean machine:

```bash
# clone this repository and move into it
cd duchenne_toolkit

# create a conda environment with all dependencies
conda env create -f environment.yml
conda activate duchenne_toolkit

# run the full pipeline
make all
```

This will download raw data, geocode care centers, fetch population counts, model DMD prevalence, compute coverage metrics, build maps and write a summary report.  All intermediate and final outputs are stored in the appropriate `data_*` and `maps` directories.

## Assumptions

* **Prevalence rates:**  We model Duchenne and Becker muscular dystrophy (DBMD) prevalence based on the [MD STARnet](https://www.cdc.gov/ncbddd/musculardystrophy/research.html) estimate of roughly 1.47 cases per 10 000 males aged 5–24 (range 1.3–1.8 per 10 000)【514519091151079†L144-L147】.  To approximate DMD only, we multiply the DBMD rate by 0.75.  As a secondary anchor, we assume a diagnosed DMD prevalence of 6 per 100 000 males aged 5–24, based on published registry data (citation to be added).  The low estimate uses the minimum of these two rates, the high estimate uses the maximum, and the mid estimate is their mean.
* **Age bands:**  We model potential patients in the 5–24 year old male population.  County‐level age‐ and sex‐specific counts come from the 2022 American Community Survey (ACS) 5‑year estimates via the Census API (table B01001).  Counts for age bands 5–9, 10–14, 15–19 and 20–24 are aggregated from the ACS variables for male 5–9, 10–14, 15–17, 18–19, 20, 21 and 22–24.
* **Population location:**  Patients are assumed to reside at the population‐weighted centroid of their county.  We use county boundary geometries from the U.S. Census Bureau’s TIGER/Line shapefiles to compute centroids.
* **Distance and drive time:**  Straight‐line (“great circle”) distance between each county centroid and each care center is computed using the haversine formula.  When available, road travel times are obtained from the OpenRouteService API; otherwise we leave drive times null and rely on distance bands.  Band definitions are ≤150 miles, 150–300 miles and >300 miles for distance, and ≤120 minutes, 120–360 minutes and >360 minutes for drive time.
* **Care center list:**  We compile a list of Priority Duchenne Care Centers (PPMD Certified Duchenne Care Centers, or CDCCs) using the PPMD 2022 Impact & Progress report and subsequent PPMD news articles announcing new certifications through 2025【681332876136906†L380-L465】【483110723608113†L430-L440】【133955900796891†L7-L21】.  This includes Boston Children’s Hospital, Norton Children’s Hospital, Penn State Health Children’s Hospital, and Children’s Hospital of Philadelphia announced in 2023–2025.  Each center is geocoded via open geocoding services.  New centers will need manual updates.
* **Equal capacity:**  All centers are treated equally without modelling their capacity or ability to take new patients.  This toolkit focuses on geographic access only and does not address wait lists, insurance limitations, or specialty availability.

## Next steps

Future versions could:

* Incorporate Muscular Dystrophy Association (MDA) Care Centers as secondary access points.
* Stratify travel burden by socioeconomic status or rurality using additional ACS variables.
* Implement a scheduled script to check the PPMD site for new care center announcements on a monthly basis.
* Perform sensitivity analyses using different prevalence rates or age bands.

## License

See the [LICENSE](LICENSE) file for usage rights.