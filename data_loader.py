
import json
import os
import csv

def load_json_or_csv(data_dir, filename):
    """
    Unified data loader.
    1. Tries to load {filename}.json
    2. If not found, tries {filename}.csv
    3. Returns list of dicts.
    """
    base_name = os.path.splitext(filename)[0]
    json_path = os.path.join(data_dir, f"{base_name}.json")
    csv_path = os.path.join(data_dir, f"{base_name}.csv")
    
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
            
    if os.path.exists(csv_path):
        data = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Basic type conversion for common fields
                if 'quantity' in row: row['quantity'] = int(row['quantity'])
                if 'progress_percent' in row: row['progress_percent'] = int(row['progress_percent'])
                if 'required_qty' in row: row['required_qty'] = int(row['required_qty'])
                if 'available_qty' in row: row['available_qty'] = int(row['available_qty'])
                if 'load_percent' in row: row['load_percent'] = int(row['load_percent'])
                # Quote fields conversion
                if 'unit_price' in row: row['unit_price'] = float(row['unit_price'])
                if 'lead_time_days' in row: row['lead_time_days'] = int(row['lead_time_days'])
                if 'moq' in row: row['moq'] = int(row['moq'])
                if 'quality_rating' in row: row['quality_rating'] = float(row['quality_rating'])
                data.append(row)
        return data
        
    return []
