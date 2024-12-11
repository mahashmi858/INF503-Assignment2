export CUDA_VISIBLE_DEVICES=0,1
MODEL=("bert" "roberta") # Generic name for models; Options: ("bert", "roberta")
DATASET="sst2"   # Dataset
MODEL_DATASET="SST-2" # Corresponding model dataset
TARGET_MODEL=("textattack/bert-base-uncased-$MODEL_DATASET" "textattack/roberta-base-$MODEL_DATASET")

RECIPE="textfooler pwws bae" # Attack options (excluding tf-adj)
EXP_NAME="lastrun" # Experiment name
PARAM_PATH="params/reduce_dim_100.json" # Model parameters
SCEN="s1"  # Scenario; Options: ("s1", "s2")
ESTIM="MCD"  # Estimator options: ("None", "MCD")

START_SEED=0
END_SEED=0
GPU=0

for ((i=0; i<${#MODEL[@]}; i++));
do
  for recipe in $RECIPE
  do
    python main.py --dataset $DATASET --model_type ${MODEL[i]} \
    --attack_type $recipe --scenario $SCEN --cov_estimator $ESTIM \
    --start_seed $START_SEED --end_seed $END_SEED --model_params_path $PARAM_PATH \
    --exp_name $EXP_NAME --gpu $GPU --target_model ${TARGET_MODEL[i]} \
    --visualize
  done
done
