import pandas as pd
import matplotlib.pyplot as plt
from tkinter import *
from tkinter import ttk, messagebox, filedialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import os

# -------------------- ANALYSIS FUNCTIONS --------------------
def analyze_dataset(file_name):
    try:
        df = pd.read_csv(file_name, parse_dates=["date"])
    except Exception as e:
        messagebox.showerror("Error", f"Cannot read file:\n{e}")
        return None

    # Clean and calculate duration
    if "start_time" in df.columns and "end_time" in df.columns:
        df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
        df["end_time"] = pd.to_datetime(df["end_time"], errors="coerce")
        df["duration_hrs"] = (df["end_time"] - df["start_time"]).dt.total_seconds() / 3600
    else:
        df["duration_hrs"] = 0

    df = df.dropna(subset=["date"])
    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M")

    return df


def plot_analysis(df):
    for widget in chart_frame.winfo_children():
        widget.destroy()

    if df is None or df.empty:
        messagebox.showwarning("No Data", "No valid data found to analyze.")
        return

    # --- Monthly Trend ---
    monthly = df.groupby("month")["duration_hrs"].sum().reset_index()
    fig1, ax1 = plt.subplots(figsize=(5, 3))
    ax1.plot(monthly["month"].astype(str), monthly["duration_hrs"], marker="o", color="blue")
    ax1.set_title("Total Load-Shedding Hours per Month")
    ax1.set_xlabel("Month")
    ax1.set_ylabel("Total Hours")
    ax1.grid(True)

    canvas1 = FigureCanvasTkAgg(fig1, master=chart_frame)
    canvas1.draw()
    canvas1.get_tk_widget().grid(row=0, column=0, padx=10, pady=10)

    # --- Weekday Pattern ---
    df["weekday"] = pd.to_datetime(df["date"]).dt.day_name()
    weekday = df.groupby("weekday")["duration_hrs"].mean().reindex(
        ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
    )
    fig2, ax2 = plt.subplots(figsize=(5, 3))
    weekday.plot(kind="bar", color="skyblue", ax=ax2)
    ax2.set_title("Average Outage Hours by Weekday")
    ax2.set_xlabel("Weekday")
    ax2.set_ylabel("Avg Hours")

    canvas2 = FigureCanvasTkAgg(fig2, master=chart_frame)
    canvas2.draw()
    canvas2.get_tk_widget().grid(row=0, column=1, padx=10, pady=10)

    # --- District Comparison ---
    if "district" in df.columns:
        district = df.groupby("district")["duration_hrs"].sum().sort_values(ascending=False)
        fig3, ax3 = plt.subplots(figsize=(5, 3))
        district.plot(kind="barh", color="salmon", ax=ax3)
        ax3.set_title("Total Outage Hours by District")
        ax3.set_xlabel("Total Hours")
        ax3.set_ylabel("District")

        canvas3 = FigureCanvasTkAgg(fig3, master=chart_frame)
        canvas3.draw()
        canvas3.get_tk_widget().grid(row=1, column=0, columnspan=2, padx=10, pady=10)

    # --- Save Summary ---
    summary = df.groupby("district")["duration_hrs"].agg(["count","mean","sum"]).reset_index()
    summary.to_csv("loadshedding_summary.csv", index=False)
    messagebox.showinfo("Success", "✅ Analysis complete!\nSummary saved to loadshedding_summary.csv")


# -------------------- UI HANDLERS --------------------
def browse_file():
    file_path = filedialog.askopenfilename(
        title="Select Load-Shedding CSV",
        filetypes=[("CSV Files", "*.csv")]
    )
    if file_path:
        dataset_var.set(file_path)

def run_analysis():
    file_name = dataset_var.get()
    if not os.path.exists(file_name):
        messagebox.showerror("Error", "Selected file not found.")
        return
    df = analyze_dataset(file_name)
    plot_analysis(df)


# -------------------- MAIN WINDOW --------------------
root = Tk()
root.title("Nepal Electricity Load-Shedding Tracker")
root.geometry("1100x750")
root.configure(bg="#f4f6f8")

# Title
title = Label(root, text="⚡ Nepal Electricity Load-Shedding Tracker",
              font=("Arial", 20, "bold"), bg="#004080", fg="white", pady=10)
title.pack(fill=X)

# Dataset selection
frame_top = Frame(root, bg="#f4f6f8")
frame_top.pack(pady=15)

Label(frame_top, text="Select Dataset:", font=("Arial", 12), bg="#f4f6f8").grid(row=0, column=0, padx=5)
dataset_var = StringVar(value="loadshedding_real.csv")

# Dataset dropdown or browse
dataset_dropdown = ttk.Combobox(frame_top, textvariable=dataset_var, width=40,
                                values=["loadshedding_real.csv", "loadshedding_sample.csv"])
dataset_dropdown.grid(row=0, column=1, padx=5)

Button(frame_top, text="Browse", command=browse_file, bg="#007acc", fg="white", padx=10).grid(row=0, column=2, padx=5)
Button(frame_top, text="Analyze", command=run_analysis, bg="#28a745", fg="white", padx=20).grid(row=0, column=3, padx=10)

# Chart area
chart_frame = Frame(root, bg="#f4f6f8")
chart_frame.pack(fill=BOTH, expand=True)

root.mainloop()
