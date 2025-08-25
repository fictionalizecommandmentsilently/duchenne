"""


# Basic validation on known columns (optional, skip silently if they don't exist)
report: Dict[str, Any] = {}
if "state_fips" in edited.columns:
bad = edited["state_fips"].astype(str).apply(validate_fips)
if (~bad).any():
report["invalid_state_fips"] = int((~bad).sum())
if "county_fips" in edited.columns:
bad = edited["county_fips"].astype(str).apply(validate_fips)
if (~bad).any():
report["invalid_county_fips"] = int((~bad).sum())
if "band_miles" in edited.columns:
edited["band_miles_norm"] = edited["band_miles"].apply(coerce_distance_band)
if edited["band_miles_norm"].isna().any():
report["invalid_band_miles"] = int(edited["band_miles_norm"].isna().sum())
else:
edited["band_miles"] = edited["band_miles_norm"]
edited = edited.drop(columns=["band_miles_norm"], errors="ignore")
# Attempt to coerce commonly numeric columns
for col in ["modeled_dmd_5_24_mid", "lat", "lon", "great_circle_mi"]:
if col in edited.columns:
coerced = pd.to_numeric(edited[col], errors="coerce")
n_nans = int(coerced.isna().sum()) - int(edited[col].isna().sum())
edited[col] = coerced
if n_nans > 0:
report[f"non_numeric_{col}"] = n_nans
# Show validation report in debug
show_validation_report(report, st)
if report:
st.error("Validation failed; please fix the issues above and try again.")
else:
# Proceed to create PR if secrets available
if missing_secrets:
st.warning(
"Cannot create pull request because required secrets are missing: "
f"{', '.join(missing_secrets)}"
)
else:
try:
repo_full_name_str: str = repo_full_name # for clarity when reading secrets
# Create a branch name and commit message
branch_name = f"data-update/{file_name.replace('.csv','')}-{pd.Timestamp.utcnow().strftime('%Y%m%d-%H%M%S')}"
base = base_branch
# Create branch
create_branch(repo_full_name_str, base, branch_name, token)
# Commit file contents
csv_bytes = edited.to_csv(index=False).encode("utf-8")
commit_file(
repo_full_name_str,
branch_name,
f"duchenne_toolkit/data_final/{file_name}",
csv_bytes,
f"chore(data): update {file_name} via Streamlit",
token,
)
# Show a simple diff preview in the UI
original = df.copy()
diff_df = edited.merge(original, how="outer", indicator=True)
st.expander("Preview: changed rows").dataframe(diff_df[diff_df["_merge"] != "both"], use_container_width=True)
# Open PR
changelog = {
"file": file_name,
"rows_before": int(len(original)),
"rows_after": int(len(edited)),
"rows_modified": int(len(diff_df)) if not diff_df.empty else 0,
}
body = "Automated data update from Streamlit app.\n\n" + json.dumps(changelog, indent=2)
pr_url = open_pr(
repo_full_name_str,
branch_name,
base,
f"feat(data): update {file_name} via app",
body,
token,
)
st.success(f"Pull request created: {pr_url}")
except Exception as exc:
st.error(f"Failed to create pull request: {exc}")
