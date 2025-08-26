import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime, timedelta
import numpy as np
from scipy import stats
from sklearn.linear_model import LinearRegression
import warnings
warnings.filterwarnings('ignore')

def visualise_data(file_path, height_cm=175, target_weight_kg=70, target_calories=2000):
    """
    Create comprehensive visualization report for Cronometer data.
    
    Args:
        file_path (str): Path to processed CSV file
        height_cm (float): User height in cm for BMI calculations
        target_weight_kg (float): Target weight for goal tracking
        target_calories (int): Target daily calories
    
    Returns:
        str: Path to generated PDF report
    """
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
    
    # Calculate macro percentages
    processed['Protein_pct'] = (processed['Protein (g)'] * 4) / processed['Energy (kcal)'] * 100
    processed['Carbs_pct'] = (processed['Carbs (g)'] * 4) / processed['Energy (kcal)'] * 100
    processed['Fat_pct'] = (processed['Fat (g)'] * 9) / processed['Energy (kcal)'] * 100
    
    # Calculate calorie deficit/surplus
    processed['Calorie_deficit'] = target_calories - processed['Energy (kcal)']
    
    # Goal tracking metrics
    processed['Days_to_goal'] = (processed['Weight (kg)'] - target_weight_kg) / processed['Weight_velocity_7d'].abs()
    processed['On_track_calories'] = (processed['Energy (kcal)'] >= (target_calories * 0.9)) & (processed['Energy (kcal)'] <= (target_calories * 1.1))
    
    # Seasonal analysis
    processed['Month'] = processed['Date'].dt.month
    processed['Weekday'] = processed['Date'].dt.dayofweek  # 0=Monday, 6=Sunday
    processed['Is_weekend'] = processed['Weekday'].isin([5, 6])
    
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

        # 6. Enhanced Nutrient Analysis
        fig, axes = plt.subplots(2, 4, figsize=(20, 10))
        axes = axes.flatten()
        
        for i, nutrient in enumerate(nutrients):
            ax = axes[i]
            # Enhanced scatter plot with trend line
            ax.scatter(processed[nutrient], processed['Daily Weight change (kg)'], alpha=0.6, color='blue')
            
            # Add trend line if correlation exists
            valid_data = ~(processed[nutrient].isna() | processed['Daily Weight change (kg)'].isna())
            if valid_data.sum() > 1:
                slope, intercept, r_value, p_value, std_err = stats.linregress(
                    processed[nutrient][valid_data], processed['Daily Weight change (kg)'][valid_data]
                )
                x_trend = np.linspace(processed[nutrient].min(), processed[nutrient].max(), 100)
                y_trend = slope * x_trend + intercept
                ax.plot(x_trend, y_trend, 'r--', alpha=0.8, 
                       label=f'R²={r_value**2:.3f}')
                ax.legend()
            
            ax.set_title(f'Weight Change vs {nutrient}', fontsize=10, fontweight='bold')
            ax.set_xlabel(nutrient)
            ax.set_ylabel('Daily Weight Change (kg)')
            ax.grid(True, alpha=0.3)
        
        # Hide unused subplot
        if len(nutrients) < len(axes):
            axes[-1].set_visible(False)
        
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
            'Protein Goal': (weekly_success['Protein (g)'] >= 100).mean() * 100,  # Assuming 100g protein goal
            'Fiber Goal': (weekly_success['Fiber (g)'] >= 25).mean() * 100   # Assuming 25g fiber goal
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

        # 9. Summary Insights and Recommendations
        fig, ax = plt.subplots(figsize=(12, 8))
        ax.axis('off')
        
        # Calculate key insights
        recent_data = processed.tail(30)
        avg_weight_change = recent_data['Daily Weight change (kg)'].mean()
        weight_trend = "losing" if avg_weight_change < -0.05 else "gaining" if avg_weight_change > 0.05 else "maintaining"
        
        strongest_predictor = weight_corrs.index[0] if len(weight_corrs) > 0 else "None"
        strongest_correlation = weight_corrs.iloc[0] if len(weight_corrs) > 0 else 0
        
        calorie_adherence = recent_data['On_track_calories'].mean() * 100
        avg_deficit = recent_data['Calorie_deficit'].mean()
        
        insights_text = f"""
        📊 BODY COMPOSITION ANALYSIS SUMMARY
        
        🎯 CURRENT STATUS
        • Weight Trend: Currently {weight_trend} weight ({avg_weight_change:+.2f} kg/day average)
        • Current Weight: {current_weight:.1f} kg | Target: {target_weight_kg} kg
        • Current BMI: {processed['BMI'].iloc[-1]:.1f} | Category: {get_bmi_category(processed['BMI'].iloc[-1])}
        
        📈 KEY INSIGHTS (Last 30 Days)
        • Strongest Weight Predictor: {strongest_predictor} (correlation: {strongest_correlation:.3f})
        • Calorie Target Adherence: {calorie_adherence:.1f}%
        • Average Daily Deficit: {avg_deficit:+.0f} calories
        • Weekend vs Weekday Difference: {weekend_data['Energy (kcal)'].mean() - weekday_data['Energy (kcal)'].mean():+.0f} calories
        
        💡 RECOMMENDATIONS
        • {"Increase calorie intake" if avg_deficit > 500 else "Maintain current calorie level" if abs(avg_deficit) < 200 else "Reduce calorie intake"}
        • Focus on {strongest_predictor.lower()} as it shows strongest correlation with weight changes
        • {"Improve weekend consistency" if abs(weekend_data['Energy (kcal)'].mean() - weekday_data['Energy (kcal)'].mean()) > 300 else "Good consistency between weekdays and weekends"}
        • Current trajectory suggests reaching target weight in ~{abs((current_weight - target_weight_kg) / (avg_weight_change if abs(avg_weight_change) > 0.01 else 0.1)):.0f} days
        
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

    return pdf_path

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
