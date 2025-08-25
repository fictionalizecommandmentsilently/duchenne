import pandas as pd
import streamlit as st
import pydeck as pdk
from pathlib import Path

st.set_page_config(page_title="Duchenne Access Coverage", layout="wide")
DATA_DIR = Path("duchenne_toolkit/data_final")

@st.cache_data
def load_data():
    centers = pd.read_csv(DATA_DIR / "centers_cdcc_us.csv", dtype={"state": str})
    cov     = pd.read_csv(DATA_DIR / "county_coverage.csv",
                          dtype={"state_fips": str, "county_fips": str})
    model   = pd.read_csv(DATA_DIR / "county_dmd_model.csv",
                          dtype={"state_fips": str, "county_fips": str})
    cov = cov.merge(
        model[["state_fips","county_fips","modeled_dmd_5_24_mid"]],
        on=["state_fips","county_fips"], how="left"
    )
    return centers, cov

centers, cov = load_data()
st.title("Duchenne Access Coverage")

states = sorted(cov["state_fips"].dropna().unique())
state_pick = st.sidebar.multiselect("Filter by state FIPS", options=states, default=states)
band_pick  = st.sidebar.multiselect("Distance band (miles)",
                                    options=["<=150","150_300",">300"],
                                    default=[">300","150_300","<=150"])
min_cases  = st.sidebar.number_input("Min modeled DMD cases (mid)",
                                     min_value=0.0, value=0.0, step=0.5)

f = cov[cov["state_fips"].isin(state_pick) &
        cov["band_miles"].isin(band_pick) &
        (cov["modeled_dmd_5_24_mid"] >= min_cases)].copy()

total = cov["modeled_dmd_5_24_mid"].sum()
sel_total = f["modeled_dmd_5_24_mid"].sum()
pct = (sel_total / total * 100) if total else 0
c1, c2, c3 = st.columns(3)
c1.metric("Total modeled DMD (mid)", f"{total:,.0f}")
c2.metric("Selected modeled DMD (mid)", f"{sel_total:,.0f}")
c3.metric("Selected share", f"{pct:0.1f}%")

def color_for_band(b):
    return {"<=150":[0,160,0], "150_300":[240,160,0], ">300":[200,0,0]}.get(b, [120,120,120])

f["color"] = f["band_miles"].apply(color_for_band)
f["radius"] = f["modeled_dmd_5_24_mid"].clip(lower=0) * 1500 + 5000

county_layer = pdk.Layer(
    "ScatterplotLayer",
    data=f,
    get_position=["centroid_lon","centroid_lat"],
    get_radius="radius",
    get_fill_color="color",
    pickable=True,
)

centers_vis = centers.dropna(subset=["lat","lon"])
center_layer = pdk.Layer(
    "ScatterplotLayer",
    data=centers_vis,
    get_position=["lon","lat"],
    get_radius=8000,
    get_fill_color=[0,0,0],
    pickable=True,
)

view = pdk.ViewState(latitude=39.5, longitude=-98.35, zoom=3.4)
st.pydeck_chart(pdk.Deck(
    layers=[county_layer, center_layer],
    initial_view_state=view,
    map_style=None,
    tooltip={"text": "{county_name}\nBand: {band_miles}\nDMD mid: {modeled_dmd_5_24_mid}"}
))

st.subheader("Top gap counties (>300 miles)")
gaps = cov[cov["band_miles"].eq(">300")].sort_values("modeled_dmd_5_24_mid", ascending=False)
st.dataframe(gaps[["state_fips","county_fips","county_name","modeled_dmd_5_24_mid",
                   "nearest_center_name","great_circle_mi"]].head(100),
             use_container_width=True)

st.subheader("Centers")
st.dataframe(centers_vis[["center_name","health_system","city","state",
                          "certification_year","website","phone"]],
             use_container_width=True)

st.download_button("Download coverage CSV", data=cov.to_csv(index=False), file_name="county_coverage.csv")
st.download_button("Download centers CSV", data=centers.to_csv(index=False), file_name="centers_cdcc_us.csv")
