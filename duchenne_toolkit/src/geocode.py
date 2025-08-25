"""Compile and geocode Certified Duchenne Care Centers.

This script defines a manual list of PPMD Certified Duchenne Care Centers
identified from the PPMD 2022 Impact & Progress report and subsequent
announcements through 2025【681332876136906†L380-L465】【483110723608113†L430-L440】【133955900796891†L7-L21】.  It geocodes each
center using the Nominatim service and outputs a CSV file with
coordinates and address components.  If geocoding fails, the script
leaves latitude and longitude blank.
"""

from __future__ import annotations

import time
import pandas as pd
from typing import List, Dict

from .config import (
    RUN_DATE,
    DATA_FINAL,
    CENTERS_OUTPUT,
    SOURCES_JSON,
)
from .utils_io import geocode_address, write_csv, save_json


def get_center_definitions() -> List[Dict[str, str]]:
    """Return a list of dictionaries defining each certified Duchenne care center.

    The fields used here are: center_name, health_system, city, state,
    certification_type (pediatric/adult), certification_year.  These
    definitions are derived from PPMD publications.  Additional fields
    such as street address and phone will be obtained via geocoding or left blank.
    """
    return [
        {"center_name": "Akron Children's Hospital", "health_system": "Akron Children's Hospital", "city": "Akron", "state": "OH", "certification_type": "Pediatric", "certification_year": 2020},
        {"center_name": "American Family Children's Hospital", "health_system": "UW Health", "city": "Madison", "state": "WI", "certification_type": "Pediatric", "certification_year": 2020},
        {"center_name": "Ann and Robert H. Lurie Children's Hospital", "health_system": "Lurie Children's", "city": "Chicago", "state": "IL", "certification_type": "Pediatric", "certification_year": 2015},
        {"center_name": "Arkansas Children's Hospital", "health_system": "Arkansas Children's", "city": "Little Rock", "state": "AR", "certification_type": "Pediatric", "certification_year": 2016},
        {"center_name": "Billings Clinic", "health_system": "Billings Clinic", "city": "Billings", "state": "MT", "certification_type": "Pediatric", "certification_year": 2022},
        {"center_name": "Children's Hospital Colorado", "health_system": "Children's Hospital Colorado", "city": "Aurora", "state": "CO", "certification_type": "Pediatric", "certification_year": 2017},
        {"center_name": "Children's Hospital of the King's Daughters", "health_system": "Children's Hospital of the King's Daughters", "city": "Norfolk", "state": "VA", "certification_type": "Pediatric", "certification_year": 2016},
        {"center_name": "Children's Hospital Los Angeles", "health_system": "Children's Hospital Los Angeles", "city": "Los Angeles", "state": "CA", "certification_type": "Pediatric", "certification_year": 2016},
        {"center_name": "Children's Hospital of Richmond at VCU", "health_system": "VCU Health", "city": "Richmond", "state": "VA", "certification_type": "Pediatric", "certification_year": 2016},
        {"center_name": "Children's Wisconsin", "health_system": "Children's Wisconsin", "city": "Milwaukee", "state": "WI", "certification_type": "Pediatric", "certification_year": 2014},
        {"center_name": "Children's Medical Center Dallas", "health_system": "UT Southwestern", "city": "Dallas", "state": "TX", "certification_type": "Pediatric", "certification_year": 2014},
        {"center_name": "Children's Mercy Hospital", "health_system": "Children's Mercy Kansas City", "city": "Kansas City", "state": "MO", "certification_type": "Pediatric", "certification_year": 2014},
        {"center_name": "Children's National Hospital", "health_system": "Children's National", "city": "Washington", "state": "DC", "certification_type": "Pediatric", "certification_year": 2014},
        {"center_name": "Cincinnati Children's Hospital Medical Center", "health_system": "Cincinnati Children's", "city": "Cincinnati", "state": "OH", "certification_type": "Pediatric", "certification_year": 2014},
        {"center_name": "Duke Children's Neuromuscular Program", "health_system": "Duke Health", "city": "Durham", "state": "NC", "certification_type": "Pediatric", "certification_year": 2017},
        {"center_name": "Helen DeVos Children's Hospital", "health_system": "Spectrum Health", "city": "Grand Rapids", "state": "MI", "certification_type": "Pediatric", "certification_year": 2017},
        {"center_name": "Kennedy Krieger Institute", "health_system": "Kennedy Krieger Institute", "city": "Baltimore", "state": "MD", "certification_type": "Pediatric", "certification_year": 2015},
        {"center_name": "Lucile Packard Children's Hospital Stanford", "health_system": "Stanford Medicine", "city": "Palo Alto", "state": "CA", "certification_type": "Pediatric", "certification_year": 2016},
        {"center_name": "Monroe Carrell Jr. Children's Hospital at Vanderbilt", "health_system": "Vanderbilt University Medical Center", "city": "Nashville", "state": "TN", "certification_type": "Pediatric", "certification_year": 2016},
        {"center_name": "Nationwide Children's Hospital", "health_system": "Nationwide Children's Hospital", "city": "Columbus", "state": "OH", "certification_type": "Pediatric", "certification_year": 2014},
        {"center_name": "Nemours Children's Health", "health_system": "Nemours Children's Health", "city": "Wilmington", "state": "DE", "certification_type": "Pediatric", "certification_year": 2016},
        {"center_name": "Phoenix Children's Hospital", "health_system": "Phoenix Children's", "city": "Phoenix", "state": "AZ", "certification_type": "Pediatric", "certification_year": 2023},
        {"center_name": "UPMC Children's Hospital of Pittsburgh", "health_system": "UPMC", "city": "Pittsburgh", "state": "PA", "certification_type": "Pediatric", "certification_year": 2016},
        {"center_name": "Riley Hospital for Children at IU Health", "health_system": "Indiana University Health", "city": "Indianapolis", "state": "IN", "certification_type": "Pediatric", "certification_year": 2016},
        {"center_name": "Seattle Children's Hospital", "health_system": "Seattle Children's", "city": "Seattle", "state": "WA", "certification_type": "Pediatric", "certification_year": 2015},
        {"center_name": "St. Louis Children's Hospital at Washington University", "health_system": "Washington University School of Medicine", "city": "St. Louis", "state": "MO", "certification_type": "Pediatric", "certification_year": 2015},
        {"center_name": "Stony Brook Children's Hospital", "health_system": "Stony Brook Medicine", "city": "Stony Brook", "state": "NY", "certification_type": "Pediatric", "certification_year": 2022},
        {"center_name": "UC Davis Health", "health_system": "UC Davis Health", "city": "Sacramento", "state": "CA", "certification_type": "Pediatric", "certification_year": 2019},
        {"center_name": "UCLA Health", "health_system": "UCLA Health", "city": "Los Angeles", "state": "CA", "certification_type": "Pediatric", "certification_year": 2015},
        {"center_name": "UCSF Benioff Children's Hospital", "health_system": "UCSF Health", "city": "San Francisco", "state": "CA", "certification_type": "Pediatric", "certification_year": 2016},
        {"center_name": "University of Iowa Stead Family Children's Hospital", "health_system": "University of Iowa Hospitals & Clinics", "city": "Iowa City", "state": "IA", "certification_type": "Pediatric", "certification_year": 2014},
        {"center_name": "University of Missouri Health Care", "health_system": "University of Missouri Health Care", "city": "Columbia", "state": "MO", "certification_type": "Pediatric", "certification_year": 2017},
        {"center_name": "University of Rochester Medical Center", "health_system": "UR Medicine", "city": "Rochester", "state": "NY", "certification_type": "Pediatric", "certification_year": 2018},
        {"center_name": "University of Utah / Primary Children's Hospital", "health_system": "University of Utah Health", "city": "Salt Lake City", "state": "UT", "certification_type": "Pediatric", "certification_year": 2015},
        {"center_name": "University of Virginia Children's Hospital", "health_system": "UVA Health", "city": "Charlottesville", "state": "VA", "certification_type": "Pediatric", "certification_year": 2015},
        {"center_name": "Yale New Haven Children's Hospital", "health_system": "Yale New Haven Health", "city": "New Haven", "state": "CT", "certification_type": "Pediatric", "certification_year": 2016},
        # New certifications announced after 2022
        {"center_name": "Boston Children's Hospital", "health_system": "Boston Children's Hospital", "city": "Boston", "state": "MA", "certification_type": "Pediatric", "certification_year": 2023},
        {"center_name": "Norton Children's Hospital", "health_system": "Norton Healthcare", "city": "Louisville", "state": "KY", "certification_type": "Pediatric", "certification_year": 2023},
        {"center_name": "Penn State Health Children's Hospital", "health_system": "Penn State Health", "city": "Hershey", "state": "PA", "certification_type": "Pediatric", "certification_year": 2024},
        {"center_name": "Children's Hospital of Philadelphia", "health_system": "Children's Hospital of Philadelphia", "city": "Philadelphia", "state": "PA", "certification_type": "Pediatric", "certification_year": 2025},
    ]


def main() -> None:
    centers = get_center_definitions()
    records = []
    sources = []
    for idx, center in enumerate(centers, start=1):
        query = f"{center['center_name']}, {center['city']}, {center['state']}, USA"
        result = geocode_address(query)
        lat = lon = None
        street = city = state = postal_code = None
        if result:
            lat, lon, raw = result
            address = raw.get("address", {})
            street = address.get("road") or address.get("house_number") or ""
            city = address.get("city") or address.get("town") or address.get("village") or center['city']
            state = address.get("state") or center['state']
            postal_code = address.get("postcode")
        # compile record
        records.append({
            "center_id": f"CDCC{idx:03d}",
            "center_name": center["center_name"],
            "health_system": center["health_system"],
            "street": street or "",
            "city": city or center["city"],
            "state": state or center["state"],
            "zip": postal_code or "",
            "lat": lat,
            "lon": lon,
            "website": "",  # website left blank; may be added manually
            "certification_type": center["certification_type"],
            "certification_year": center["certification_year"],
            "phone": "",  # phone numbers not included in PPMD dataset
            "notes": "Geocoded using Nominatim",  # note geocoding method
            "data_source": "PPMD Certified Duchenne Care Center announcements",  # general source
            "source_retrieved_date": RUN_DATE,
        })
        # record citation metadata for sources.json (for manual citations only; not exhaustive)
        sources.append({
            "center_name": center["center_name"],
            "data_source": "PPMD publications",
            "retrieved_date": RUN_DATE,
        })
        # Respect courtesy delay between geocoding requests
        time.sleep(1)
    df = pd.DataFrame(records)
    write_csv(CENTERS_OUTPUT, df)
    # Save a simple list of sources
    save_json(SOURCES_JSON, {"centers": sources})
    print(f"Wrote {len(df)} centers to {CENTERS_OUTPUT}")


if __name__ == "__main__":
    main()