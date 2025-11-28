import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LinearSegmentedColormap
from datetime import datetime, timedelta
import numpy as np
from scipy import stats
from sklearn.linear_model import LinearRegression
import warnings
import os
from dotenv import load_dotenv
warnings.filterwarnings('ignore')

# Load environment variables - they are now passed through docker-compose
# load_dotenv() is not needed since variables are in container environment

def visualise_data(file_path):
    """
    Create comprehensive visualization report for Cronometer data.
    Parameters are loaded from environment variables.
    
    Args:
        file_path (str): Path to processed CSV file
    
    Returns:
        str: Path to generated PDF report
    """
    # Load parameters from environment variables with defaults
    height_cm = float(os.getenv('USER_HEIGHT_CM', 175))
    target_weight_kg = float(os.getenv('TARGET_WEIGHT_KG', 70))
    target_calories = int(os.getenv('TARGET_CALORIES', 2000))
    protein_goal_g = int(os.getenv('PROTEIN_GOAL_G', 100))
    fiber_goal_g = int(os.getenv('FIBER_GOAL_G', 25))
    calorie_tolerance_pct = float(os.getenv('CALORIE_TOLERANCE_PCT', 0.1))  # 10% tolerance by default
    
    # Debug: Print loaded values to verify .env is working
    print(f"DEBUG: Loaded TARGET_WEIGHT_KG = {target_weight_kg}")
    print(f"DEBUG: Loaded USER_HEIGHT_CM = {height_cm}")
    print(f"DEBUG: Loaded TARGET_CALORIES = {target_calories}")
    # Load the cleaned CSV file
    processed = pd.read_csv(file_path)

    # Convert the 'Date' column to datetime format
    processed['Date'] = pd.to_datetime(processed['Date'])
    
    # Sort by date to ensure proper chronological order
    processed = processed.sort_values('Date').reset_index(drop=True)

    # Save the plot as an image file
    the_time = datetime.now().strftime("%Y-%m-%d_%H-%M")

    nutrients = ['Energy (kcal)', 'Protein (g)', 'Carbs (g)', 'Fat (g)', 'Fiber (g)', 'Sodium (mg)', 'Water (g)']
    
    # Calculate BMI and additional metrics
    processed['BMI'] = processed['Weight (kg)'] / ((height_cm / 100) ** 2)
    processed['BMI_7_avg'] = processed['BMI'].rolling(7, min_periods=3).mean()
    processed['BMI_30_avg'] = processed['BMI'].rolling(30, min_periods=7).mean()
    
    # Calculate weight velocity (rate of change)
    processed['Weight_velocity_7d'] = processed['Weight (kg)'].rolling(7).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0] * 7 if len(x) >= 3 else np.nan)
    processed['Weight_velocity_30d'] = processed['Weight (kg)'].rolling(30).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0] * 30 if len(x) >= 7 else np.nan)
    
    # Calculate macro percentages (avoid division by zero)
    processed['Protein_pct'] = np.where(processed['Energy (kcal)'] > 0, 
                                        (processed['Protein (g)'] * 4) / processed['Energy (kcal)'] * 100, 0)
    processed['Carbs_pct'] = np.where(processed['Energy (kcal)'] > 0,
                                      (processed['Carbs (g)'] * 4) / processed['Energy (kcal)'] * 100, 0)
    processed['Fat_pct'] = np.where(processed['Energy (kcal)'] > 0,
                                    (processed['Fat (g)'] * 9) / processed['Energy (kcal)'] * 100, 0)
    
    # Calculate calorie deficit/surplus
    processed['Calorie_deficit'] = target_calories - processed['Energy (kcal)']
    
    # Goal tracking metrics (avoid division by zero)
    processed['Days_to_goal'] = np.where(processed['Weight_velocity_7d'].abs() > 0.001,
                                         (processed['Weight (kg)'] - target_weight_kg) / processed['Weight_velocity_7d'].abs(),
                                         np.nan)
    processed['On_track_calories'] = (processed['Energy (kcal)'] >= (target_calories * (1 - calorie_tolerance_pct))) & (processed['Energy (kcal)'] <= (target_calories * (1 + calorie_tolerance_pct)))
    
    # Seasonal analysis
    processed['Month'] = processed['Date'].dt.month
    processed['Weekday'] = processed['Date'].dt.dayofweek  # 0=Monday, 6=Sunday
    processed['Is_weekend'] = processed['Weekday'].isin([5, 6])
    
    # Calculate TDEE estimates
    tdee_estimates = estimate_tdee(processed)
    
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

    average_nutrition_3 = filtered_data[nutrients].mean()

    # Create a dictionary to hold the data
    data = {
        "Nutrient": nutrients,
        "Weight Gain Days All Time": avg_nutrients_gain_all.values,
        "Weight Loss Days All Time": avg_nutrients_loss_all.values,
        "Weight Gain Days 3 Months": avg_nutrients_gain_3.values,
        "Weight Loss Days 3 Months": avg_nutrients_loss_3.values,
        "Average Nutrition 3 Months": average_nutrition_3.values
    }

    # Create a DataFrame
    df = pd.DataFrame(data)

    # Creating the PDF report
    pdf_path = f"/opt/airflow/csvs/analytics_report_{the_time}.pdf"
    with PdfPages(pdf_path) as pdf:
        
        # 1. BMI Tracking & Trends
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # BMI over time with category zones
        ax1.plot(processed['Date'], processed['BMI'], label='Daily BMI', alpha=0.6, color='lightblue')
        ax1.plot(processed['Date'], processed['BMI_7_avg'], label='7-day avg', color='blue', linewidth=2)
        ax1.plot(processed['Date'], processed['BMI_30_avg'], label='30-day avg', color='darkblue', linewidth=2)
        
        # BMI category zones
        ax1.axhspan(0, 18.5, alpha=0.2, color='lightcoral', label='Underweight')
        ax1.axhspan(18.5, 25, alpha=0.2, color='lightgreen', label='Normal')
        ax1.axhspan(25, 30, alpha=0.2, color='orange', label='Overweight')
        ax1.axhspan(30, 50, alpha=0.2, color='red', label='Obese')
        
        ax1.set_title('BMI Tracking with Health Categories', fontsize=14, fontweight='bold')
        ax1.set_ylabel('BMI')
        ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax1.grid(True, alpha=0.3)
        
        # Weight with trend line
        ax2.plot(processed['Date'], processed['Weight (kg)'], label='Daily Weight', alpha=0.6, color='lightgreen')
        
        # Add trend line using linear regression
        if len(processed) > 1:
            days_numeric = (processed['Date'] - processed['Date'].min()).dt.days
            valid_data = ~(processed['Weight (kg)'].isna() | days_numeric.isna())
            if valid_data.sum() > 1:
                slope, intercept, r_value, p_value, std_err = stats.linregress(
                    days_numeric[valid_data], processed['Weight (kg)'][valid_data]
                )
                trend_line = slope * days_numeric + intercept
                ax2.plot(processed['Date'], trend_line, '--', color='red', linewidth=2, 
                        label=f'Trend (R²={r_value**2:.3f})')
        
        # Target weight line
        ax2.axhline(y=target_weight_kg, color='purple', linestyle=':', linewidth=2, label='Target Weight')
        
        ax2.set_title('Weight Progress with Trend Analysis', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Weight (kg)')
        ax2.set_ylim(100, 140)
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)
        
        # 2. Weight Velocity Analysis
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # Weight velocity charts
        ax1.plot(processed['Date'], processed['Weight_velocity_7d'], label='7-day velocity', color='blue')
        ax1.plot(processed['Date'], processed['Weight_velocity_30d'], label='30-day velocity', color='orange')
        ax1.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        ax1.set_title('Weight Change Velocity (kg/period)', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Weight Change Rate')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Days to goal estimation
        valid_days_to_goal = processed['Days_to_goal'].replace([np.inf, -np.inf], np.nan)
        ax2.plot(processed['Date'], valid_days_to_goal, color='purple', alpha=0.7)
        ax2.set_title('Estimated Days to Target Weight', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Days to Goal')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)
        
        # 3. Macro Nutrition Analysis
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        
        # Macro percentages over time
        ax1.plot(processed['Date'], processed['Protein_pct'], label='Protein %', color='red')
        ax1.plot(processed['Date'], processed['Carbs_pct'], label='Carbs %', color='orange')
        ax1.plot(processed['Date'], processed['Fat_pct'], label='Fat %', color='blue')
        ax1.set_title('Macronutrient Percentages Over Time', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Percentage of Calories')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Average macro pie chart
        recent_data = processed.tail(30)  # Last 30 days
        avg_macros = [
            recent_data['Protein_pct'].mean(),
            recent_data['Carbs_pct'].mean(), 
            recent_data['Fat_pct'].mean()
        ]
        colors = ['#ff6b6b', '#ffa726', '#42a5f5']
        ax2.pie(avg_macros, labels=['Protein', 'Carbs', 'Fat'], colors=colors, autopct='%1.1f%%')
        ax2.set_title('Average Macro Distribution (Last 30 Days)', fontsize=12, fontweight='bold')
        
        # Calorie deficit/surplus
        ax3.bar(processed['Date'], processed['Calorie_deficit'], 
               color=['green' if x > 0 else 'red' for x in processed['Calorie_deficit']], alpha=0.7)
        ax3.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        ax3.set_title('Daily Calorie Deficit/Surplus', fontsize=12, fontweight='bold')
        ax3.set_ylabel('Calories vs Target')
        ax3.grid(True, alpha=0.3)
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)
        
        # Calorie adherence percentage
        adherence_rate = processed['On_track_calories'].rolling(7).mean() * 100
        ax4.plot(processed['Date'], adherence_rate, color='green', linewidth=2)
        ax4.set_title('7-Day Calorie Target Adherence Rate', fontsize=12, fontweight='bold')
        ax4.set_ylabel('Adherence Rate (%)')
        ax4.set_ylim(0, 100)
        ax4.grid(True, alpha=0.3)
        plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)
        
        # 4. Seasonal and Weekly Patterns
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        
        # Monthly patterns
        monthly_weight = processed.groupby('Month')['Weight (kg)'].mean()
        monthly_calories = processed.groupby('Month')['Energy (kcal)'].mean()
        
        ax1.bar(monthly_weight.index, monthly_weight.values, color='lightblue', alpha=0.7)
        ax1.set_title('Average Weight by Month', fontsize=12, fontweight='bold')
        ax1.set_xlabel('Month')
        ax1.set_ylabel('Weight (kg)')
        ax1.set_xticks(range(1, 13))
        
        ax2.bar(monthly_calories.index, monthly_calories.values, color='orange', alpha=0.7)
        ax2.set_title('Average Calories by Month', fontsize=12, fontweight='bold')
        ax2.set_xlabel('Month')
        ax2.set_ylabel('Calories')
        ax2.set_xticks(range(1, 13))
        
        # Weekday vs Weekend patterns
        weekday_data = processed[~processed['Is_weekend']]
        weekend_data = processed[processed['Is_weekend']]
        
        categories = ['Weight (kg)', 'Energy (kcal)', 'Protein (g)', 'Carbs (g)', 'Fat (g)']
        weekday_means = [weekday_data[cat].mean() for cat in categories]
        weekend_means = [weekend_data[cat].mean() for cat in categories]
        
        x = np.arange(len(categories))
        width = 0.35
        
        ax3.bar(x - width/2, weekday_means, width, label='Weekdays', alpha=0.7)
        ax3.bar(x + width/2, weekend_means, width, label='Weekends', alpha=0.7)
        ax3.set_title('Weekday vs Weekend Patterns', fontsize=12, fontweight='bold')
        ax3.set_xticks(x)
        ax3.set_xticklabels(categories, rotation=45)
        ax3.legend()
        
        # Weight change distribution
        ax4.hist(processed['Daily Weight change (kg)'].dropna(), bins=30, alpha=0.7, color='purple')
        ax4.axvline(x=0, color='red', linestyle='--', alpha=0.7)
        ax4.set_title('Daily Weight Change Distribution', fontsize=12, fontweight='bold')
        ax4.set_xlabel('Weight Change (kg)')
        ax4.set_ylabel('Frequency')
        
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # 5. Original Energy and Weight Plot (Enhanced)
        fig, ax1 = plt.subplots(figsize=(12, 6))
        ax1.plot(processed['Date'], processed['Energy 7 days avg (kcal)'], label='7 Days Avg', color='blue', linewidth=2)
        ax1.plot(processed['Date'], processed['Energy 30 days avg (kcal)'], label='30 Days Avg', color='orange', linewidth=2)
        ax1.axhline(y=target_calories, color='red', linestyle=':', alpha=0.7, label='Target Calories')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Energy (kcal)', color='blue')
        ax1.set_title('Energy Intake Rolling Averages with Weight Overlay', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_locator(mdates.MonthLocator())
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
        
        ax2 = ax1.twinx()
        ax2.plot(processed['Date'], processed["Weight (kg)"], label='Weight', color='green', linewidth=2)
        ax2.set_ylabel('Weight (kg)', color='green')
        ax2.set_ylim(100, 140)
        ax2.legend(loc='upper right')
        
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # 6. Consolidated Nutrient Analysis
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
        
        # Define colors for each nutrient
        nutrient_colors = {
            'Energy (kcal)': '#e74c3c',      # Red
            'Protein (g)': '#3498db',         # Blue
            'Carbs (g)': '#f39c12',           # Orange
            'Fat (g)': '#9b59b6',             # Purple
            'Fiber (g)': '#2ecc71',           # Green
            'Sodium (mg)': '#1abc9c',         # Teal
            'Water (g)': '#34495e'            # Dark Gray
        }
        
        # Top chart: Rolling 14-day correlations between each nutrient and weight change
        window_size = 14
        for nutrient in nutrients:
            # Calculate rolling correlation
            rolling_corr = processed[nutrient].rolling(window_size).corr(
                processed['Daily Weight change (kg)']
            )
            ax1.plot(processed['Date'], rolling_corr, 
                    label=nutrient.replace(' (', '\n('), 
                    color=nutrient_colors.get(nutrient, 'gray'),
                    linewidth=1.5, alpha=0.8)
        
        ax1.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        ax1.axhline(y=0.3, color='green', linestyle='--', alpha=0.3, label='Strong +')
        ax1.axhline(y=-0.3, color='red', linestyle='--', alpha=0.3, label='Strong -')
        ax1.set_title('Rolling 14-Day Correlation: Nutrients vs Weight Change', 
                     fontsize=12, fontweight='bold')
        ax1.set_ylabel('Correlation Coefficient')
        ax1.set_ylim(-1, 1)
        ax1.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=8)
        ax1.grid(True, alpha=0.3)
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
        
        # Bottom chart: Static correlation bar chart with significance
        correlations_list = []
        for nutrient in nutrients:
            valid_mask = ~(processed[nutrient].isna() | processed['Daily Weight change (kg)'].isna())
            if valid_mask.sum() > 2:
                corr, p_value = stats.pearsonr(
                    processed[nutrient][valid_mask], 
                    processed['Daily Weight change (kg)'][valid_mask]
                )
                correlations_list.append({
                    'nutrient': nutrient,
                    'correlation': corr,
                    'p_value': p_value,
                    'significant': p_value < 0.05
                })
        
        # Sort by absolute correlation
        correlations_list.sort(key=lambda x: abs(x['correlation']), reverse=True)
        
        # Create horizontal bar chart
        y_positions = range(len(correlations_list))
        bar_colors = [nutrient_colors.get(item['nutrient'], 'gray') for item in correlations_list]
        edge_colors = ['black' if item['significant'] else 'none' for item in correlations_list]
        
        bars = ax2.barh(y_positions, [item['correlation'] for item in correlations_list],
                       color=bar_colors, alpha=0.7, edgecolor=edge_colors, linewidth=2)
        
        ax2.set_yticks(y_positions)
        ax2.set_yticklabels([item['nutrient'] for item in correlations_list])
        ax2.axvline(x=0, color='black', linestyle='-', alpha=0.5)
        ax2.set_xlabel('Correlation with Daily Weight Change')
        ax2.set_title('Overall Nutrient-Weight Correlations (black border = statistically significant)', 
                     fontsize=12, fontweight='bold')
        ax2.set_xlim(-0.5, 0.5)
        ax2.grid(True, alpha=0.3, axis='x')
        
        # Add correlation values on bars
        for i, item in enumerate(correlations_list):
            x_pos = item['correlation'] + (0.02 if item['correlation'] >= 0 else -0.02)
            ha = 'left' if item['correlation'] >= 0 else 'right'
            ax2.text(x_pos, i, f"{item['correlation']:.3f}", va='center', ha=ha, fontsize=9)
        
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # 7. Enhanced Correlation Matrix with Insights
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        
        # Correlation heatmap
        sns.heatmap(correlations, annot=True, cmap="RdBu_r", center=0, vmin=-1, vmax=1, ax=ax1)
        ax1.set_title('Correlation Matrix: Weight Change vs Nutrients', fontsize=12, fontweight='bold')
        
        # Top correlations bar chart
        weight_corrs = correlations['Daily Weight change (kg)'].drop('Daily Weight change (kg)').abs().sort_values(ascending=False)
        colors = ['green' if correlations['Daily Weight change (kg)'][nutrient] > 0 else 'red' for nutrient in weight_corrs.index]
        ax2.barh(range(len(weight_corrs)), weight_corrs.values, color=colors, alpha=0.7)
        ax2.set_yticks(range(len(weight_corrs)))
        ax2.set_yticklabels([label.replace(' (', '\n(') for label in weight_corrs.index])
        ax2.set_xlabel('Absolute Correlation with Weight Change')
        ax2.set_title('Strongest Predictors of Weight Change', fontsize=12, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='x')
        
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # 8. Goal Progress Dashboard
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        
        # Weight progress toward goal
        current_weight = processed['Weight (kg)'].iloc[-1] if len(processed) > 0 else target_weight_kg
        weight_progress = max(0, min(100, (1 - abs(current_weight - target_weight_kg) / abs(processed['Weight (kg)'].iloc[0] - target_weight_kg)) * 100)) if len(processed) > 0 else 0
        
        ax1.pie([weight_progress, 100-weight_progress], labels=['Progress', 'Remaining'], 
               colors=['green', 'lightgray'], autopct='%1.1f%%', startangle=90)
        ax1.set_title(f'Weight Goal Progress\nCurrent: {current_weight:.1f}kg | Target: {target_weight_kg}kg', 
                     fontsize=12, fontweight='bold')
        
        # Calorie adherence streak
        recent_adherence = processed['On_track_calories'].tail(30)
        streak_count = 0
        for val in reversed(recent_adherence.values):
            if val:
                streak_count += 1
            else:
                break
        
        ax2.bar(['Current Streak', 'Best Possible'], [streak_count, 30], 
               color=['green', 'lightgray'], alpha=0.7)
        ax2.set_title(f'Calorie Target Adherence Streak\n{streak_count} days', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Days')
        
        # Weekly success metrics
        weekly_success = processed.tail(7)
        metrics = {
            'Calorie Target': weekly_success['On_track_calories'].mean() * 100,
            'Weight Stable': (weekly_success['Daily Weight change (kg)'].abs() < 0.5).mean() * 100,
            'Protein Goal': (weekly_success['Protein (g)'] >= protein_goal_g).mean() * 100,
            'Fiber Goal': (weekly_success['Fiber (g)'] >= fiber_goal_g).mean() * 100
        }
        
        ax3.bar(metrics.keys(), metrics.values(), color=['blue', 'green', 'red', 'orange'], alpha=0.7)
        ax3.set_title('Weekly Success Metrics (%)', fontsize=12, fontweight='bold')
        ax3.set_ylabel('Success Rate (%)')
        ax3.set_ylim(0, 100)
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)
        
        # Trend prediction
        if len(processed) > 7:
            recent_weights = processed['Weight (kg)'].tail(30).dropna()
            if len(recent_weights) > 1:
                days = np.arange(len(recent_weights))
                slope, intercept = np.polyfit(days, recent_weights, 1)
                future_days = np.arange(len(recent_weights), len(recent_weights) + 30)
                predicted_weights = slope * future_days + intercept
                
                ax4.plot(days, recent_weights, 'o-', label='Actual', color='blue')
                ax4.plot(future_days, predicted_weights, '--', label='Predicted', color='red')
                ax4.axhline(y=target_weight_kg, color='green', linestyle=':', label='Target')
                ax4.set_title('30-Day Weight Prediction', fontsize=12, fontweight='bold')
                ax4.set_xlabel('Days')
                ax4.set_ylabel('Weight (kg)')
                ax4.legend()
                ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # 9. Calorie Adherence Calendar Heatmap
        fig, ax = plt.subplots(figsize=(16, 10))
        
        # Prepare calendar data - last 12 months or all available data
        calendar_data = processed[['Date', 'On_track_calories', 'Energy (kcal)', 'Calorie_deficit']].copy()
        calendar_data['Year'] = calendar_data['Date'].dt.year
        calendar_data['Month'] = calendar_data['Date'].dt.month
        calendar_data['Day'] = calendar_data['Date'].dt.day
        calendar_data['Week'] = calendar_data['Date'].dt.isocalendar().week
        calendar_data['Weekday'] = calendar_data['Date'].dt.weekday  # 0=Monday, 6=Sunday
        
        # Create adherence status: 1=on track, 0.5=under, 0=over
        def get_adherence_status(row):
            if row['On_track_calories']:
                return 1.0  # On track (green)
            elif row['Calorie_deficit'] > 0:
                return 0.5  # Under target (yellow)
            else:
                return 0.0  # Over target (red)
        
        calendar_data['Status'] = calendar_data.apply(get_adherence_status, axis=1)
        
        # Get the last 6 months of data for cleaner visualization
        six_months_ago = calendar_data['Date'].max() - timedelta(days=180)
        recent_calendar = calendar_data[calendar_data['Date'] >= six_months_ago].copy()
        
        if len(recent_calendar) > 0:
            # Create a pivot for the heatmap - weeks as columns, weekdays as rows
            # Group by year-week to handle year boundaries
            recent_calendar['YearWeek'] = recent_calendar['Date'].dt.strftime('%Y-W%V')
            
            # Create matrix for heatmap
            unique_weeks = recent_calendar['YearWeek'].unique()
            week_order = sorted(unique_weeks)
            
            # Create empty matrix (7 weekdays x number of weeks)
            heatmap_matrix = np.full((7, len(week_order)), np.nan)
            
            for _, row in recent_calendar.iterrows():
                week_idx = week_order.index(row['YearWeek'])
                weekday_idx = row['Weekday']
                heatmap_matrix[weekday_idx, week_idx] = row['Status']
            
            # Create custom colormap: red (over) -> yellow (under) -> green (on track)
            colors_list = ['#e74c3c', '#f39c12', '#2ecc71']  # Red, Yellow, Green
            cmap = LinearSegmentedColormap.from_list('adherence', colors_list, N=256)
            
            # Plot heatmap
            im = ax.imshow(heatmap_matrix, cmap=cmap, aspect='auto', vmin=0, vmax=1)
            
            # Set labels
            weekday_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            ax.set_yticks(range(7))
            ax.set_yticklabels(weekday_labels)
            
            # Show month labels instead of week numbers
            month_positions = []
            month_labels = []
            current_month = None
            for i, week in enumerate(week_order):
                # Parse week to get approximate month
                week_dates = recent_calendar[recent_calendar['YearWeek'] == week]['Date']
                if len(week_dates) > 0:
                    month = week_dates.iloc[0].strftime('%b %Y')
                    if month != current_month:
                        month_positions.append(i)
                        month_labels.append(month)
                        current_month = month
            
            ax.set_xticks(month_positions)
            ax.set_xticklabels(month_labels, rotation=45, ha='right')
            
            # Add colorbar legend
            cbar = plt.colorbar(im, ax=ax, shrink=0.5, aspect=20)
            cbar.set_ticks([0, 0.5, 1])
            cbar.set_ticklabels(['Over Target', 'Under Target', 'On Track'])
            
            # Calculate summary statistics
            total_days = len(recent_calendar)
            on_track_days = (recent_calendar['Status'] == 1.0).sum()
            under_days = (recent_calendar['Status'] == 0.5).sum()
            over_days = (recent_calendar['Status'] == 0.0).sum()
            
            # Add summary text
            summary_text = (
                f"Last 6 Months Summary:\n"
                f"✅ On Track: {on_track_days} days ({on_track_days/total_days*100:.1f}%)\n"
                f"⚠️ Under Target: {under_days} days ({under_days/total_days*100:.1f}%)\n"
                f"❌ Over Target: {over_days} days ({over_days/total_days*100:.1f}%)"
            )
            ax.text(1.15, 0.5, summary_text, transform=ax.transAxes, fontsize=11,
                   verticalalignment='center', fontfamily='monospace',
                   bbox=dict(boxstyle="round,pad=0.5", facecolor="white", alpha=0.9))
            
            ax.set_title('Calorie Adherence Calendar Heatmap (Last 6 Months)', 
                        fontsize=14, fontweight='bold')
        else:
            ax.text(0.5, 0.5, 'Insufficient data for calendar heatmap', 
                   transform=ax.transAxes, ha='center', va='center', fontsize=14)
            ax.set_title('Calorie Adherence Calendar Heatmap', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # 10. Summary Insights and Recommendations
        fig, ax = plt.subplots(figsize=(12, 8))
        ax.axis('off')
        
        # Calculate key insights
        recent_data = processed.tail(30)
        avg_weight_change = recent_data['Daily Weight change (kg)'].mean()
        if pd.isna(avg_weight_change):
            avg_weight_change = 0
        weight_trend = "losing" if avg_weight_change < -0.05 else "gaining" if avg_weight_change > 0.05 else "maintaining"
        
        strongest_predictor = weight_corrs.index[0] if len(weight_corrs) > 0 else "None"
        strongest_correlation = weight_corrs.iloc[0] if len(weight_corrs) > 0 else 0
        
        calorie_adherence = recent_data['On_track_calories'].mean() * 100
        if pd.isna(calorie_adherence):
            calorie_adherence = 0
        avg_deficit = recent_data['Calorie_deficit'].mean()
        if pd.isna(avg_deficit):
            avg_deficit = 0
        
        insights_text = f"""
{{ ... }}
        📊 BODY COMPOSITION ANALYSIS SUMMARY
        
        🎯 CURRENT STATUS
        • Weight Trend: Currently {weight_trend} weight ({avg_weight_change:+.2f} kg/day average)
        • Current Weight: {current_weight:.1f} kg | Target: {target_weight_kg} kg
        • Current BMI: {processed['BMI'].iloc[-1]:.1f} | Category: {get_bmi_category(processed['BMI'].iloc[-1]) if not pd.isna(processed['BMI'].iloc[-1]) else 'Unknown'}
        
        📈 KEY INSIGHTS (Last 30 Days)
        • Strongest Weight Predictor: {strongest_predictor} (correlation: {strongest_correlation:.3f})
        • Calorie Target Adherence: {calorie_adherence:.1f}%
        • Average Daily Deficit: {avg_deficit:+.0f} calories
        • Weekend vs Weekday Difference: {(weekend_data['Energy (kcal)'].mean() - weekday_data['Energy (kcal)'].mean()) if len(weekend_data) > 0 and len(weekday_data) > 0 else 0:+.0f} calories
        
        💡 RECOMMENDATIONS
        • {"Increase calorie intake" if avg_deficit > 500 else "Maintain current calorie level" if abs(avg_deficit) < 200 else "Reduce calorie intake"}
        • Focus on {strongest_predictor.lower()} as it shows strongest correlation with weight changes
        • {"Improve weekend consistency" if len(weekend_data) > 0 and len(weekday_data) > 0 and abs(weekend_data['Energy (kcal)'].mean() - weekday_data['Energy (kcal)'].mean()) > 300 else "Good consistency between weekdays and weekends"}
        • Current trajectory suggests reaching target weight in ~{abs((current_weight - target_weight_kg) / (avg_weight_change if abs(avg_weight_change) > 0.01 else 0.1)) if abs(avg_weight_change) > 0.001 else 'N/A'} days
        
        📋 SUMMARY TABLE
        """
        
        ax.text(0.05, 0.95, insights_text, transform=ax.transAxes, fontsize=11, 
               verticalalignment='top', fontfamily='monospace',
               bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.8))
        
        # Add the enhanced summary data table
        table_data = df.round(1)
        table = ax.table(cellText=table_data.values, colLabels=table_data.columns, 
                        cellLoc='center', loc='lower center', 
                        colColours=["#e1f5fe"]*len(table_data.columns))
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.2, 1.5)
        
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # 11. TDEE Analysis Dashboard
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        
        # TDEE estimates comparison
        if tdee_estimates:
            methods = []
            values = []
            colors = []
            
            method_colors = {
                'weighted_average': '#2E8B57',  # Sea Green
                'energy_balance_30d': '#4682B4',  # Steel Blue
                'energy_balance_14d': '#6495ED',  # Cornflower Blue
                'stable_weight_periods': '#FF6347',  # Tomato
                'regression': '#9370DB',  # Medium Purple
                'recent_30d': '#20B2AA'  # Light Sea Green
            }
            
            for method, estimate in tdee_estimates.items():
                if method not in ['stable_periods_count', 'regression_r2'] and isinstance(estimate, (int, float)) and 1200 < estimate < 4000:
                    methods.append(method.replace('_', ' ').title())
                    values.append(estimate)
                    colors.append(method_colors.get(method, '#808080'))
            
            if methods:
                bars = ax1.bar(range(len(methods)), values, color=colors, alpha=0.7)
                ax1.set_xticks(range(len(methods)))
                ax1.set_xticklabels(methods, rotation=45, ha='right')
                ax1.set_title('TDEE Estimates by Method', fontsize=12, fontweight='bold')
                ax1.set_ylabel('Calories per Day')
                ax1.grid(True, alpha=0.3, axis='y')
                
                # Add value labels on bars
                for bar, value in zip(bars, values):
                    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
                            f'{value:.0f}', ha='center', va='bottom', fontsize=9)
        
        # TDEE over time (rolling estimates)
        if 'TDEE_7d' in processed.columns:
            ax2.plot(processed['Date'], processed['TDEE_7d'], label='7-day TDEE', alpha=0.7, color='blue')
            ax2.plot(processed['Date'], processed['TDEE_14d'], label='14-day TDEE', alpha=0.7, color='orange')
            ax2.plot(processed['Date'], processed['TDEE_30d'], label='30-day TDEE', alpha=0.7, color='green')
            
            if 'weighted_average' in tdee_estimates:
                ax2.axhline(y=tdee_estimates['weighted_average'], color='red', linestyle='--', 
                           label=f'Est. TDEE: {tdee_estimates["weighted_average"]:.0f}')
            
            ax2.set_title('TDEE Estimates Over Time', fontsize=12, fontweight='bold')
            ax2.set_ylabel('Calories per Day')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
        
        # Calorie intake vs TDEE comparison
        recent_data = processed.tail(30)
        avg_intake = recent_data['Energy (kcal)'].mean()
        
        if 'weighted_average' in tdee_estimates:
            estimated_tdee = tdee_estimates['weighted_average']
            surplus_deficit = avg_intake - estimated_tdee
            
            categories = ['Average Intake', 'Estimated TDEE']
            values = [avg_intake, estimated_tdee]
            colors = ['lightblue', 'lightcoral']
            
            bars = ax3.bar(categories, values, color=colors, alpha=0.7)
            ax3.set_title('Intake vs TDEE (Last 30 Days)', fontsize=12, fontweight='bold')
            ax3.set_ylabel('Calories per Day')
            
            # Add value labels
            for bar, value in zip(bars, values):
                ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
                        f'{value:.0f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
            
            # Add surplus/deficit annotation
            color = 'green' if surplus_deficit > 0 else 'red'
            ax3.text(0.5, max(values) * 0.5, f'{"Surplus" if surplus_deficit > 0 else "Deficit"}:\n{abs(surplus_deficit):.0f} cal/day',
                    ha='center', va='center', fontsize=12, fontweight='bold', color=color,
                    bbox=dict(boxstyle="round,pad=0.3", facecolor=color, alpha=0.2))
        
        # TDEE confidence and method summary
        ax4.axis('off')
        
        if tdee_estimates:
            summary_text = "🔥 TDEE ESTIMATION SUMMARY\n\n"
            
            if 'weighted_average' in tdee_estimates:
                summary_text += f"📊 Best Estimate: {tdee_estimates['weighted_average']:.0f} cal/day\n\n"
            
            summary_text += "📈 Method Results:\n"
            
            method_names = {
                'energy_balance_30d': '30-day Energy Balance',
                'energy_balance_14d': '14-day Energy Balance',
                'stable_weight_periods': 'Stable Weight Periods',
                'regression': 'Regression Analysis',
                'recent_30d': 'Recent 30 Days'
            }
            
            for method, name in method_names.items():
                if method in tdee_estimates and isinstance(tdee_estimates[method], (int, float)) and 1200 < tdee_estimates[method] < 4000:
                    summary_text += f"• {name}: {tdee_estimates[method]:.0f} cal\n"
            
            if 'stable_periods_count' in tdee_estimates:
                summary_text += f"\n📋 Data Quality:\n"
                summary_text += f"• Stable weight periods: {tdee_estimates['stable_periods_count']}\n"
            
            if 'regression_r2' in tdee_estimates:
                summary_text += f"• Regression R²: {tdee_estimates['regression_r2']:.3f}\n"
            
            summary_text += f"\n💡 Recommendations:\n"
            if 'weighted_average' in tdee_estimates:
                est_tdee = tdee_estimates['weighted_average']
                if avg_intake > est_tdee + 200:
                    summary_text += "• Consider reducing intake for weight loss\n"
                elif avg_intake < est_tdee - 200:
                    summary_text += "• Consider increasing intake\n"
                else:
                    summary_text += "• Current intake appears well-balanced\n"
                
                summary_text += f"• For weight loss: ~{est_tdee - 500:.0f} cal/day\n"
                summary_text += f"• For weight gain: ~{est_tdee + 300:.0f} cal/day"
            
            ax4.text(0.05, 0.95, summary_text, transform=ax4.transAxes, fontsize=10,
                    verticalalignment='top', fontfamily='monospace',
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow", alpha=0.8))
        
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    return pdf_path

def estimate_tdee(processed_data):
    """
    Estimate Total Daily Energy Expenditure using multiple methods.
    
    Args:
        processed_data (DataFrame): Processed nutrition and weight data
        
    Returns:
        dict: TDEE estimates from different methods
    """
    tdee_estimates = {}
    
    # Method 1: Energy Balance Method (most periods)
    # TDEE = Calories In - (Weight Change × 7700 kcal/kg) / days
    valid_data = processed_data.dropna(subset=['Energy (kcal)', 'Daily Weight change (kg)'])
    
    if len(valid_data) > 7:
        # 7-day rolling TDEE calculation
        def calculate_energy_balance_tdee(window_data):
            if len(window_data) < 3:
                return np.nan
            
            avg_calories = window_data['Energy (kcal)'].mean()
            total_weight_change = window_data['Daily Weight change (kg)'].sum()
            days = len(window_data)
            
            # 7700 kcal ≈ 1 kg of fat
            weight_change_calories = total_weight_change * 7700 / days
            tdee = avg_calories - weight_change_calories
            
            return tdee
        
        # Calculate rolling TDEE estimates using a different approach
        def calculate_rolling_tdee(data, window_size, min_periods):
            """Calculate rolling TDEE using energy balance method."""
            tdee_values = []
            
            for i in range(len(data)):
                start_idx = max(0, i - window_size + 1)
                end_idx = i + 1
                
                if end_idx - start_idx < min_periods:
                    tdee_values.append(np.nan)
                    continue
                
                window_data = data.iloc[start_idx:end_idx]
                avg_calories = window_data['Energy (kcal)'].mean()
                total_weight_change = window_data['Daily Weight change (kg)'].sum()
                days = len(window_data)
                
                # 7700 kcal ≈ 1 kg of fat
                weight_change_calories = total_weight_change * 7700 / days
                tdee = avg_calories - weight_change_calories
                tdee_values.append(tdee)
            
            return pd.Series(tdee_values, index=data.index)
        
        energy_weight_data = processed_data[['Energy (kcal)', 'Daily Weight change (kg)']]
        
        # Calculate rolling TDEE estimates
        processed_data['TDEE_7d'] = calculate_rolling_tdee(energy_weight_data, 7, 3)
        processed_data['TDEE_14d'] = calculate_rolling_tdee(energy_weight_data, 14, 7)
        processed_data['TDEE_30d'] = calculate_rolling_tdee(energy_weight_data, 30, 14)
        
        # Overall energy balance TDEE
        avg_calories = valid_data['Energy (kcal)'].mean()
        total_weight_change = valid_data['Daily Weight change (kg)'].sum()
        days = len(valid_data)
        weight_change_calories = total_weight_change * 7700 / days
        
        tdee_estimates['energy_balance'] = avg_calories - weight_change_calories
        tdee_estimates['energy_balance_7d'] = processed_data['TDEE_7d'].dropna().mean()
        tdee_estimates['energy_balance_14d'] = processed_data['TDEE_14d'].dropna().mean()
        tdee_estimates['energy_balance_30d'] = processed_data['TDEE_30d'].dropna().mean()
    
    # Method 2: Stable Weight Periods
    # Find periods where weight change is minimal (±0.2kg over 7 days)
    if len(processed_data) > 7:
        stable_periods = []
        window_size = 7
        
        for i in range(len(processed_data) - window_size + 1):
            window = processed_data.iloc[i:i+window_size]
            weight_range = window['Weight (kg)'].max() - window['Weight (kg)'].min()
            
            if weight_range <= 0.4:  # ±0.2kg tolerance
                avg_calories = window['Energy (kcal)'].mean()
                if not np.isnan(avg_calories) and avg_calories > 0:
                    stable_periods.append(avg_calories)
        
        if stable_periods:
            tdee_estimates['stable_weight_periods'] = np.mean(stable_periods)
            tdee_estimates['stable_periods_count'] = len(stable_periods)
    
    # Method 3: Regression Analysis
    # Find calorie intake that results in zero weight change
    if len(valid_data) > 14:
        try:
            from sklearn.linear_model import LinearRegression
            
            X = valid_data[['Energy (kcal)']].values
            y = valid_data['Daily Weight change (kg)'].values
            
            model = LinearRegression()
            model.fit(X, y)
            
            # Find calorie level where weight change = 0
            if abs(model.coef_[0]) > 1e-6:  # Avoid division by zero
                tdee_regression = -model.intercept_ / model.coef_[0]
                if 1000 < tdee_regression < 5000:  # Sanity check
                    tdee_estimates['regression'] = tdee_regression
                    tdee_estimates['regression_r2'] = model.score(X, y)
        except:
            pass
    
    # Method 4: Recent Period Analysis (last 30 days)
    recent_data = processed_data.tail(30)
    recent_valid = recent_data.dropna(subset=['Energy (kcal)', 'Daily Weight change (kg)'])
    
    if len(recent_valid) > 7:
        avg_calories = recent_valid['Energy (kcal)'].mean()
        total_weight_change = recent_valid['Daily Weight change (kg)'].sum()
        days = len(recent_valid)
        weight_change_calories = total_weight_change * 7700 / days
        
        tdee_estimates['recent_30d'] = avg_calories - weight_change_calories
    
    # Calculate confidence-weighted average
    if tdee_estimates:
        # Weight different methods based on data quality and period length
        weights = {}
        values = {}
        
        if 'energy_balance_30d' in tdee_estimates:
            weights['energy_balance_30d'] = 0.3
            values['energy_balance_30d'] = tdee_estimates['energy_balance_30d']
        
        if 'energy_balance_14d' in tdee_estimates:
            weights['energy_balance_14d'] = 0.25
            values['energy_balance_14d'] = tdee_estimates['energy_balance_14d']
        
        if 'stable_weight_periods' in tdee_estimates:
            weights['stable_weight_periods'] = 0.2
            values['stable_weight_periods'] = tdee_estimates['stable_weight_periods']
        
        if 'regression' in tdee_estimates and tdee_estimates.get('regression_r2', 0) > 0.1:
            weights['regression'] = 0.15
            values['regression'] = tdee_estimates['regression']
        
        if 'recent_30d' in tdee_estimates:
            weights['recent_30d'] = 0.1
            values['recent_30d'] = tdee_estimates['recent_30d']
        
        if values:
            # Filter out unrealistic values
            realistic_values = {k: v for k, v in values.items() if 1200 < v < 4000}
            
            if realistic_values:
                weighted_sum = sum(realistic_values[k] * weights.get(k, 0.1) for k in realistic_values)
                total_weight = sum(weights.get(k, 0.1) for k in realistic_values)
                tdee_estimates['weighted_average'] = weighted_sum / total_weight
    
    return tdee_estimates

def get_bmi_category(bmi):
    """Return BMI category based on value."""
    if bmi < 18.5:
        return "Underweight"
    elif bmi < 25:
        return "Normal"
    elif bmi < 30:
        return "Overweight"
    else:
        return "Obese"
