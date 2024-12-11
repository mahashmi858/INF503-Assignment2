#!/usr/bin/env bash

export CUDA_VISIBLE_DEVICES=0,1

# We'll test with bert and roberta models on the yelp dataset (using Yelp Polarity models)
MODELS=("bert" "roberta")

# Use the yelp dataset name as before
DATASET="yelp"
MODEL_DATASET="yelp" 

# Attacks that are present for yelp (from your previous listings)
# Yelp had: textfooler, pwws, bae, tf-adj
RECIPE="textfooler pwws bae tf-adj"

EXP_NAME="all"
PARAM_PATH="params/reduce_dim_100.json"
SCEN="s1"
ESTIM="MCD"
START_SEED=0
END_SEED=0
GPU=0

for MODEL_TYPE in "${MODELS[@]}"
do
    # Use the polarity models from TextAttack 
    # Confirm these models exist at: https://huggingface.co/models?q=textattack
    if [ "$MODEL_TYPE" = "bert" ]; then
        TARGET_MODEL="textattack/bert-base-uncased-yelp-polarity"
    elif [ "$MODEL_TYPE" = "roberta" ]; then
        TARGET_MODEL="textattack/roberta-base-yelp-polarity"
    fi

    for recipe in $RECIPE
    do
        python main.py \
        --dataset $DATASET \
        --model_type $MODEL_TYPE \
        --attack_type $recipe \
        --scenario $SCEN \
        --cov_estimator $ESTIM \
        --start_seed $START_SEED \
        --end_seed $END_SEED \
        --model_params_path $PARAM_PATH \
        --exp_name $EXP_NAME \
        --gpu $GPU \
        --target_model $TARGET_MODEL \
        --visualize
    done
done
