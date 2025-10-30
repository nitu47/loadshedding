# analyze_loadshedding.py
import pandas as pd
import matplotlib.pyplot as plt
import os

# --- Step 1: Choose dataset ---
print("📂 Available datasets:")
for f in ["loadshedding_real.csv", "loadshedding_sample.csv"]:
    if os.path.exists(f):
        print(f"  ✅ {f}")
choice = input("\nEnter dataset name to analyze (press Enter for 'loadshedding_real.csv'): ").strip()

if choice == "":
    choice = "loadshedding_real.csv"

if not os.path.exists(choice):
    print(f"❌ File '{choice}' not found in this folder!")
    exit()

print(f"\n📊 Using dataset: {choice}\n")

# --- Step 2: Load data ---
try:
    df = pd.read_csv(choice, parse_dates=["date"])
except Exception as e:
    print(f"⚠️ Error loading CSV: {e}")
    exit()

# --- Step 3: Clean and calculate duration ---
if "start_time" in df.columns and "end_time" in df.columns:
    df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
    df["end_time"] = pd.to_datetime(df["end_time"], errors="coerce")
    df["duration_hrs"] = (df["end_time"] - df["start_time"]).dt.total_seconds() / 3600
else:
    print("⚠️ 'start_time' or 'end_time' columns missing; skipping duration calculation.")
    df["duration_hrs"] = 0

df = df.dropna(subset=["date"])
df["month"] = pd.to_datetime(df["date"]).dt.to_period("M")

# --- Step 4: Monthly trend ---
monthly = df.groupby("month")["duration_hrs"].sum().reset_index()

plt.figure(figsize=(9, 5))
plt.plot(monthly["month"].astype(str), monthly["duration_hrs"], marker="o", color="blue")
plt.title("Total Load-Shedding Hours per Month (NEA Trend)")
plt.xlabel("Month")
plt.ylabel("Total Hours")
plt.grid(True)
plt.tight_layout()
plt.show()

# --- Step 5: Weekday pattern ---
df["weekday"] = pd.to_datetime(df["date"]).dt.day_name()
weekday = df.groupby("weekday")["duration_hrs"].mean().reindex(
    ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
)

plt.figure(figsize=(8, 4))
weekday.plot(kind="bar", color="skyblue")
plt.title("Average Outage Hours by Weekday")
plt.xlabel("Weekday")
plt.ylabel("Average Hours")
plt.tight_layout()
plt.show()

# --- Step 6: District-wise total outage ---
if "district" in df.columns:
    district = df.groupby("district")["duration_hrs"].sum().sort_values(ascending=False)
    plt.figure(figsize=(8, 5))
    district.plot(kind="barh", color="salmon")
    plt.title("Total Outage Hours by District")
    plt.xlabel("Total Hours")
    plt.ylabel("District")
    plt.tight_layout()
    plt.show()

# --- Step 7: Save summary ---
summary = df.groupby("district")["duration_hrs"].agg(["count", "mean", "sum"]).reset_index()
summary.to_csv("loadshedding_summary.csv", index=False)
print("✅ Analysis complete! Summary saved to loadshedding_summary.csv")
