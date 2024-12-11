#!/usr/bin/env bash

export CUDA_VISIBLE_DEVICES=0  # Single GPU

MODELS=("bert" "roberta")
DATASETS=("imdb" "ag-news" "sst2" "yelp")

EXP_NAME="final_experiment"
PARAM_PATH="params/reduce_dim_100.json"
SCEN="s1"
ESTIM="MCD"
START_SEED=0
END_SEED=1
GPU=0

for DATASET in "${DATASETS[@]}"; do
    if [ "$DATASET" = "sst2" ]; then
       MODEL_DATASET="SST-2"
    else
       MODEL_DATASET="$DATASET"
    fi

    if [ "$DATASET" = "sst2" ]; then
        RECIPE="textfooler pwws"
    elif [ "$DATASET" = "yelp" ]; then
        RECIPE="textfooler pwws"
    else
        RECIPE="textfooler pwws"
    fi

    for MODEL_TYPE in "${MODELS[@]}"; do
        if [ "$MODEL_TYPE" = "bert" ]; then
            if [ "$DATASET" = "yelp" ]; then
                TARGET_MODEL="textattack/bert-base-uncased-yelp-polarity"
            else
                TARGET_MODEL="textattack/bert-base-uncased-$MODEL_DATASET"
            fi
        elif [ "$MODEL_TYPE" = "roberta" ]; then
            if [ "$DATASET" = "yelp" ]; then
                TARGET_MODEL="textattack/roberta-base-yelp-polarity"
            else
                TARGET_MODEL="textattack/roberta-base-$MODEL_DATASET"
            fi
        fi

        for recipe in $RECIPE; do
            for SEED in $(seq $START_SEED $END_SEED); do
                python main.py \
                --dataset $DATASET \
                --model_type $MODEL_TYPE \
                --attack_type $recipe \
                --scenario $SCEN \
                --cov_estimator $ESTIM \
                --start_seed $SEED \
                --end_seed $SEED \
                --model_params_path $PARAM_PATH \
                --exp_name $EXP_NAME \
                --gpu $GPU \
                --target_model $TARGET_MODEL \
                --visualize
            done
        done
    done
done
