import pandas as pd

def process_csv(file_path1, file_path2):
    # Load the CSV files
    # file_path1: Path to the first CSV file (nutrition data)
    # file_path2: Path to the second CSV file (bio data)
    nutrition = pd.read_csv(file_path1)
    bio = pd.read_csv(file_path2)

    # Perform data cleaning and processing on the 'bio' DataFrame
    # Rename columns for consistency and clarity
    bio.rename(columns={"Day":"Date"}, inplace=True)
    bio.rename(columns={"Amount":"Weight (kg)"}, inplace=True)
    
    # Filter rows where the 'Unit' column is 'kg'
    bio_cleaned = bio[bio["Unit"]=="kg"]
    
    # Convert 'Date' column to datetime format for both DataFrames
    bio_cleaned["Date"] = pd.to_datetime(bio_cleaned["Date"])
    nutrition["Date"] = pd.to_datetime(nutrition["Date"])
    
    # Drop the 'Completed' column from the 'nutrition' DataFrame as it's not needed
    nutrition = nutrition.drop(columns=["Completed"])
    
    # Drop the 'Unit' and 'Metric' columns from the cleaned 'bio' DataFrame as they're not needed
    bio_cleaned = bio_cleaned.drop(columns=["Unit", "Metric"])
    
    # Merge the 'nutrition' and cleaned 'bio' DataFrames on the 'Date' column
    # Use a left join to retain all rows from the 'nutrition' DataFrame
    processed = pd.merge(nutrition, bio_cleaned, how="left")
    
    # Fill any missing values with 0
    processed = processed.fillna(0)

    # Create new columns for rolling Calorie average 7 days and 30 days
    processed["Energy 7 days avg (kcal)"] = processed["Energy (kcal)"].rolling(7).mean()
    processed["Energy 30 days avg (kcal)"] = processed["Energy (kcal)"].rolling(30).mean()

    # Create a new column for daily weight change
    processed["Daily Weight change (kg)"] = processed["Weight (kg)"] - processed["Weight (kg)"].shift(1)
    
    # Save the cleaned and merged data to a new CSV file
    file_path = "C:\\Airflow Project\\processes.csv"
    processed.to_csv(path_or_buf=file_path, index=False)

    # Return the path to the saved CSV file
    return file_path
