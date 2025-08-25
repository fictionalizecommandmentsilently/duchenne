PYTHON=python3
SRC_DIR=src

.PHONY: all setup fetch_data build_model coverage maps report clean

all: fetch_data build_model coverage maps report

setup:
	@echo "Creating necessary directories..."
	mkdir -p data_raw data_intermediate data_final docs maps

# Download or scrape the care center list and raw population data
fetch_data:
	$(PYTHON) $(SRC_DIR)/geocode.py
	$(PYTHON) $(SRC_DIR)/fetch_acs.py

# Build the county‐level DMD model
build_model:
	$(PYTHON) $(SRC_DIR)/model_dmd.py

# Compute nearest center and coverage bands
coverage:
	$(PYTHON) $(SRC_DIR)/coverage.py

# Generate interactive and static maps
maps:
	$(PYTHON) $(SRC_DIR)/maps.py

# Produce the markdown summary report
report:
	$(PYTHON) $(SRC_DIR)/report.py

clean:
	rm -rf data_intermediate data_final maps docs/*