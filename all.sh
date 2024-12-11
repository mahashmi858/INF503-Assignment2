#!/usr/bin/env bash

export CUDA_VISIBLE_DEVICES=0,1

# Models to test
MODELS=("bert" "roberta" "cnn" "lstm")

# Datasets to test
DATASETS=("imdb" "ag-news" "sst2" "yelp")

EXP_NAME="all"
PARAM_PATH="params/reduce_dim_100.json"
SCEN="s1"
ESTIM="MCD"
START_SEED=0
END_SEED=0
GPU=0

for DATASET in "${DATASETS[@]}"
do
    # Set MODEL_DATASET for SST-2; otherwise use the dataset name as is
    if [ "$DATASET" = "sst2" ]; then
       MODEL_DATASET="SST-2"
    else
       MODEL_DATASET="$DATASET"
    fi

    # Determine attacks based on dataset
    # For sst2: skip tf-adj
    # For yelp: no pruthi
    # imdb, ag-news: all attacks including pruthi
    if [ "$DATASET" = "sst2" ]; then
        RECIPE="textfooler pwws bae pruthi"
    elif [ "$DATASET" = "yelp" ]; then
        RECIPE="textfooler pwws bae tf-adj"
    else
        RECIPE="textfooler pwws bae tf-adj pruthi"
    fi

    for MODEL_TYPE in "${MODELS[@]}"
    do
        # Determine target model name
        if [ "$MODEL_TYPE" = "bert" ]; then
            TARGET_MODEL="textattack/bert-base-uncased-$MODEL_DATASET"
        elif [ "$MODEL_TYPE" = "roberta" ]; then
            TARGET_MODEL="textattack/roberta-base-$MODEL_DATASET"
        else
            # For cnn and lstm, adjust as necessary if you have local models
            TARGET_MODEL="$MODEL_TYPE-$DATASET"
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
done
