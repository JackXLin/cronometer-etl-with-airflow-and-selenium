import pandas as pd
import matplotlib.pyplot as plt

def visualise_data(file_path):
    # Load the cleaned CSV file
    df = pd.read_csv(file_path)

    # Create a simple plot (e.g., calories over time)
    plt.figure()
    plt.plot(df['Date'], df['Weight (kg)'], label='Weight (kg)', color='blue')
    plt.plot(df['Date'], df['Energy (kcal)'], label='Energy (kcal)', color='red')
    
    # Add labels and legend
    plt.xlabel('Date')
    plt.ylabel('Value')
    plt.legend()

    # Save the plot as an image file
    save_path = r"/opt/airflow/csvs/visualisation.png"
    plt.savefig(save_path)
    print(f"Plot saved to {save_path}")
    return save_path
