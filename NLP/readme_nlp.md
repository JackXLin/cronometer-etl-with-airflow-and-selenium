# Food Classification with RoBERTa and NVIDIA 4090

## Project Overview

This project aims to classify food items as either **"Junk"** or **"Not Junk"** using the **RoBERTa** pre-trained language model, fine-tuned on a custom dataset of food names and their corresponding categories. The fine-tuning process leverages the power of an **NVIDIA 4090 GPU** for faster training using mixed-precision and other optimisations.

## Hardware Used

- **GPU**: NVIDIA GeForce RTX 4090
  - Enabled **mixed precision training** for faster model training and reduced memory usage.
  - Used PyTorch with CUDA 11.8 to fully utilize the 4090 GPU’s capabilities.

## Steps Taken

### 1. **Setup for Using the NVIDIA 4090**

We configured the training environment to utilise the GPU for faster processing. To ensure this, we installed **PyTorch with CUDA support** and verified the GPU availability using:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```
In the code, we ensured that the model and data were moved to the GPU using the following checks:

```python
import torch

# Check if GPU is available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Move model to GPU (if available)
model.to(device)
```

### 2. Data Preprocessing

We created a function to combine the food name and its category into a single string, giving the model more contextual information for better classification.

```python
def preprocess_food_name_with_category(food_name, category):
    # Concatenate food name with category
    return f"{food_name}, {category}"

data['combined_input'] = data.apply(lambda row: preprocess_food_name_with_category(row['Food Name'], row['Category']), axis=1)
```

### 3. Switch to RoBERTa

We replaced BERT with RoBERTa to optimize performance. RoBERTa has better optimisation compared to BERT, leading to better performance in many NLP tasks.

```python
from transformers import RobertaTokenizer, RobertaForSequenceClassification

# Load RoBERTa tokenizer and model
tokenizer = RobertaTokenizer.from_pretrained('roberta-base')
model = RobertaForSequenceClassification.from_pretrained('roberta-base', num_labels=2)
```

### 4. Fine-Tuning with NVIDIA 4090 and Mixed Precision

We fine-tuned the RoBERTa model using Hugging Face’s Trainer API, leveraging the 4090’s computational power. We also enabled mixed precision training (fp16) to speed up the process.

```python
from transformers import Trainer, TrainingArguments

training_args = TrainingArguments(
    output_dir='./results',
    num_train_epochs=3,
    per_device_train_batch_size=16,  # Adjusted batch size for the 4090
    per_device_eval_batch_size=16,
    logging_dir='./logs',
    evaluation_strategy="epoch",
    fp16=True  # Mixed precision enabled for faster training
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,  # Replace with your dataset
    eval_dataset=eval_dataset      # Replace with your evaluation data
)

# Fine-tuning the model
trainer.train()
```

### 5. Model Inference and Classification

After fine-tuning, we used the trained model to classify new food items. The combined food name and category were passed to the tokenizer for encoding and then classified by the model.

```python
def classify_food_item(item, category):
    # Combine food name and category
    combined_input = f"{item}, {category}"
    
    # Tokenize and encode
    encoding = tokenizer(combined_input, truncation=True, padding=True, max_length=64, return_tensors='pt').to(device)
    
    # Make prediction
    outputs = model(**encoding)
    logits = outputs.logits
    
    # Get the predicted class
    predicted_class = torch.argmax(logits, dim=1).item()
    return 'Junk' if predicted_class == 1 else 'Not Junk'
```

### Example Usage

You can classify a new food item with its category like this:

```python
new_item = "Apple"
category = "Fruit"
classification = classify_food_item_with_corrections(new_item, category)
print(f"The item '{new_item}' is classified as: {classification}")

```

### Installation

To run the project, you need the following libraries installed:
```python
pip install transformers torch pandas
```
See top of this readme for GPU support

# Running the Model

1. **Prepare the Dataset**: Ensure that your dataset has columns for `Food Name`, `Category`, and `Label`. The food name and category will be combined as input.
2. **Fine-tune the Model**: Use the provided training script to fine-tune the model on your dataset, utilizing the NVIDIA 4090 for accelerated training.
3. **Inference**: Classify new food items after fine-tuning using the provided classification function.

# Hardware Optimization

- **Mixed Precision Training**: Enabled through the `fp16=True` flag in the `TrainingArguments` to leverage the GPU’s capabilities.
- **Batch Size Tuning**: The batch size was increased to 16 due to the large memory capacity of the 4090.

# Future Work

1. **Data Augmentation**: Further improve the dataset by adding more examples, especially for edge cases.
2. **Larger Models**: Experiment with `roberta-large` to see if the larger model improves classification accuracy.


