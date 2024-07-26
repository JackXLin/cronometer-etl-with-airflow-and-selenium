import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime, timedelta

def visualise_data(file_path):
    # Load the cleaned CSV file
    processed = pd.read_csv(file_path)

    # Convert the 'Date' column to datetime format
    processed['Date'] = pd.to_datetime(processed['Date'])

    # Save the plot as an image file
    the_time = datetime.now().strftime("%Y-%m-%d_%H-%M")

    nutrients = ['Energy (kcal)', 'Protein (g)', 'Carbs (g)', 'Fat (g)', 'Fiber (g)', 'Sodium (mg)', 'Water (g)']
    
    # Compute the correlation matrix
    correlations = processed[['Daily Weight change (kg)'] + nutrients].corr()

    # Filter data for the last 3 months
    three_months_ago = datetime.now() - timedelta(days=90)
    filtered_data = processed[processed["Date"] >= three_months_ago]

    weight_gain_days_all = processed[processed['Daily Weight change (kg)'] > 0]
    weight_loss_days_all = processed[processed['Daily Weight change (kg)'] < 0]

    avg_nutrients_gain_all = weight_gain_days_all[nutrients].mean()
    avg_nutrients_loss_all = weight_loss_days_all[nutrients].mean()

    weight_gain_days_3 = filtered_data[filtered_data['Daily Weight change (kg)'] > 0]
    weight_loss_days_3 = filtered_data[filtered_data['Daily Weight change (kg)'] < 0]

    avg_nutrients_gain_3 = weight_gain_days_3[nutrients].mean()
    avg_nutrients_loss_3= weight_loss_days_3[nutrients].mean()

    average_autrition_3 = filtered_data[nutrients].mean()

    # Create a dictionary to hold the data
    data = {
        "Nutrient": nutrients,
        "Weight Gain Days All Time": avg_nutrients_gain_all.values,
        "Weight Loss Days All Time": avg_nutrients_loss_all.values,
        "Weight Gain Days 3 Months": avg_nutrients_gain_3.values,
        "Weight Loss Days 3 Months": avg_nutrients_loss_3.values,
        "Average Nutrition 3 Months": average_autrition_3.values
    }

    # Create a DataFrame
    df = pd.DataFrame(data)

    # Creating the PDF report
    pdf_path = f"/opt/airflow/csvs/analytics_report_{the_time}.pdf"
    with PdfPages(pdf_path) as pdf:
        # Add the rolling averages plot
        fig, ax1 = plt.subplots(figsize=(12, 6))
        ax1.plot(processed['Date'], processed['Energy 7 days avg (kcal)'], label='7 Days Avg', color='blue')
        ax1.plot(processed['Date'], processed['Energy 30 days avg (kcal)'], label='30 Days Avg', color='orange')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Energy (kcal)')
        ax1.set_title('Energy Intake Rolling Averages')
        ax1.legend(loc='upper left')
        ax1.grid(True)
        ax1.xaxis.set_major_locator(mdates.MonthLocator())
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
        ax2 = ax1.twinx()
        ax2.plot(processed['Date'], processed["Weight (kg)"], label='Weight', color='green')
        ax2.set_ylabel('Weight (kg)')
        ax2.set_ylim(100, 140)
        ax2.legend(loc='upper right')
        pdf.savefig(fig)
        plt.close(fig)

        # Add scatter plots of Weight vs. Nutrient Intake
        for nutrient in nutrients:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.scatter(processed[nutrient], processed['Daily Weight change (kg)'])
            ax.set_title(f'Weight vs {nutrient}')
            ax.set_xlabel(nutrient)
            ax.set_ylabel('Weight (kg)')
            ax.grid(True)
            pdf.savefig(fig)
            plt.close(fig)

        # Add the correlation matrix
        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(correlations, annot=True, cmap="Blues", vmin=-1, vmax=1, ax=ax)
        ax.set_title('Correlation Matrix')
        pdf.savefig(fig)
        plt.close(fig)

        # Add the summary data table
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.axis('tight')
        ax.axis('off')
        table_data = df.round(1)
        table = ax.table(cellText=table_data.values, colLabels=table_data.columns, cellLoc='center', loc='center', colColours=["#f2f2f2"]*len(table_data.columns))
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.2)
        pdf.savefig(fig)
        plt.close(fig)

    return pdf_path
