export CUDA_VISIBLE_DEVICES=0,1
MODEL=("bert" "roberta") # Generic name for models; Options: ("bert", "roberta")

DATASETS=("imdb" "sst2")  # Options: ("imdb", "sst2")
MODEL_DATASETS=("imdb" "SST-2") # Corresponding model datasets
TARGET_MODELS=("textattack/bert-base-uncased-" "textattack/roberta-base-")

RECIPE="textfooler pwws bae tf-adj" # Four attack options (No tf-adj for SST-2 dataset)
EXP_NAME="lastrun" # Name for experiment
PARAM_PATH="params/reduce_dim_100.json" # Indicate model parameters (e.g., No PCA, linear PCA, MLE)
SCEN="s1"  # Scenario (see paper for details); Options: ("s1", "s2")
ESTIM="MCD"  # Options: ("None", "MCD")

START_SEED=0
END_SEED=0
GPU=0

for ((j=0; j<${#DATASETS[@]}; j++));
do
  DATASET=${DATASETS[j]}
  MODEL_DATASET=${MODEL_DATASETS[j]}

  for ((i=0; i<${#MODEL[@]}; i++));
  do
    for recipe in $RECIPE
    do
      # Skip "tf-adj" for SST-2 since it is not applicable
      if [[ $DATASET == "sst2" && $recipe == "tf-adj" ]]; then
        continue
      fi

      python main.py --dataset $DATASET --model_type ${MODEL[i]} \
      --attack_type $recipe --scenario $SCEN --cov_estimator $ESTIM \
      --start_seed $START_SEED --end_seed $END_SEED --model_params_path $PARAM_PATH \
      --exp_name $EXP_NAME --gpu $GPU --target_model ${TARGET_MODELS[i]}$MODEL_DATASET \
      --visualize
    done
  done
done
