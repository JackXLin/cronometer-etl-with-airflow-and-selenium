import pandas as pd
import matplotlib.pyplot as plt

def visualise_data(file_path):
    # Load the cleaned CSV file
    processed = pd.read_csv(file_path)

    # Create the first plot
    fig, ax1 = plt.subplots(figsize=(12, 6))

    ax1.plot(processed['Date'], processed['Energy 7 days avg (kcal)'], label='7 Days Avg', color='blue')
    ax1.plot(processed['Date'], processed['Energy 30 days avg (kcal)'], label='30 Days Avg', color='orange')
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Energy (kcal)')
    ax1.set_title('Energy Intake Rolling Averages')
    ax1.legend(loc='upper left')
    ax1.grid(True)

    # Create a second y-axis sharing the same x-axis
    ax2 = ax1.twinx()
    ax2.plot(processed['Date'], processed["Weight (kg)"], label='Weight', color='green')
    ax2.set_ylabel('Weight (kg)')
    ax2.set_ylim(100, 140)
    ax2.legend(loc='upper right')

    # Save the plot as an image file
    save_path = r"/opt/airflow/csvs/visualisation.png"
    plt.savefig(save_path)
    print(f"Plot saved to {save_path}")
    return save_path
