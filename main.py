import argparse
import json
import time
import pdb


parser = argparse.ArgumentParser(description="Detect and defense attacked samples")

parser.add_argument("--dataset", default="imdb", type=str,
                    choices=["ag-news", "imdb", "yelp", "mnli", "sst2"],
                    help="classification dataset to use")
parser.add_argument("--target_model", default="textattack/bert-base-uncased-imdb", type=str,
                    help="name of model (textattack pretrained model, path to ckpt)")
parser.add_argument("--model_type", type=str, help="model type (e.g. bert, roberta, cnn)")

parser.add_argument("--scenario", type=str, help="scenario that determines how the configure the adv. dataset")
parser.add_argument("--include_fae", default=False, action='store_true', help="Include failed adversarial examples for detection as well")
parser.add_argument("--use_val", default=False, action='store_true')
parser.add_argument("--cov_estimator", type=str, help="covariance estimator",
                    choices=["OAS", "MCD", "None"])

parser.add_argument("--attack_type", default='textfooler', type=str,
                    help="attack type for logging")
parser.add_argument("--exp_name", default='tmp', type=str,
                    help="Name for logging")

parser.add_argument("--fpr_threshold", default=0.10)
parser.add_argument("--baseline", default=False, action="store_true")
parser.add_argument("--visualize", default=False, action="store_true")

parser.add_argument("--model_params_path", type=str, default="params/reduce_dim_false.json",
                    help="path to json file containing params about probability modeling")
parser.add_argument("--PCA_dim", type=int, default=None,
                    help="Reduced dimension of kPCA. If None, determined by params json file")
parser.add_argument("--MCD_h", type=float, default=None,
                    help="Support fraction h of MCD. If None, the default value is used.")

parser.add_argument("--gpu", default='0', type=str)
parser.add_argument("--start_seed", default=0, type=int)
parser.add_argument("--end_seed", default=0, type=int)
parser.add_argument("--mnli_option", default="matched", type=str,
                    choices=["matched", "mismatched"],
                    help="use matched or mismatched test set for MNLI")
#Options for FGWS settings
parser.add_argument("--preprocess", default="standard", type=str,
                    choices=["standard", "fgws"])
parser.add_argument("--data_type", default="standard", type=str,
                    choices=["standard", "fgws"])
parser.add_argument("--pkl_test_path", default=" ", type=str,
                    help="perturbed texts files with extension csv or pkl")
parser.add_argument("--pkl_val_path", default=" ", type=str,
                    help="perturbed texts files with extension csv or pkl")


args, _ = parser.parse_known_args()


from utils.detection import *
from utils.dataset import *
from utils.logger import *
from utils.miscellaneous import *
from models.wrapper import BertWrapper
from Detector import Detector
from AttackLoader import AttackLoader

model_type = args.target_model.replace("/","-")
if args.exp_name:
  args.log_path = f"runs/{args.dataset}/{args.exp_name}/{model_type}/{args.attack_type}"
else:
  args.log_path = f"runs/{args.dataset}/{model_type}/{args.attack_type}"

if __name__ == "__main__":
  if not os.path.isdir(args.log_path):
    os.makedirs(args.log_path)
  logger = Logger(args.log_path)
  logger.log.info("Args: "+str(args.__dict__))

  with open(args.model_params_path, "r") as r:
    params = json.load(r)
  if args.PCA_dim:
    params['reduce_dim']['dim'] = args.PCA_dim
  params['h'] = float(args.MCD_h) if args.MCD_h else None
  num_params = len(glob.glob(os.path.join(args.log_path, "*.json")))
  with open(os.path.join(args.log_path, f"params-{num_params}.json"), "w") as w:
    json.dump(params, w)
  logger.log.info("Using params...")
  logger.log.info(params)

  model_wrapper = BertWrapper(args, logger)
  model = model_wrapper.model
  tokenizer = model_wrapper.tokenizer
  model.eval()

  trainvalset, _, key = get_dataset(args)
  text_key, testset_key = key
  trainset, _ = split_dataset(trainvalset, split='trainval', split_ratio=0.8)
  # Get features from the train set. Load from pickle if exists
  feats = get_train_features(model_wrapper, args, batch_size=256, dataset=trainset, text_key=text_key, layer=params['layer_param']['cls_layer'])
  feats = feats.numpy()
  s_time = time.time()
  reduced_feat, labels, reducer, scaler = preprocess_features(feats, params, args, logger)

  train_stats, estimators = get_stats(reduced_feat, labels, cov_estim_name=args.cov_estimator, use_shared_cov=params['shared_cov'], params=params)
  naive_train_stats, naive_estimators = get_stats(reduced_feat, labels, cov_estim_name="None", use_shared_cov=params['shared_cov'])
  all_train_stats = [naive_train_stats, train_stats]
  all_estimators = [naive_estimators, estimators]
  logger.log.info(f"Elapsed time for model fitting : {time.time()-s_time}")


  if args.visualize:
    dir_name = os.path.dirname(args.log_path)
    path_to_feat = os.path.join(dir_name, 'feats.txt')
    feat_n_label = np.concatenate([reduced_feat, labels[:,np.newaxis]], axis=-1)
    np.savetxt(path_to_feat, feat_n_label)
    for cls_idx, mu_n_cov in enumerate(train_stats):
      np.save(os.path.join(dir_name, f"cls{cls_idx}-cov.npy"), mu_n_cov[1])

    for name, stat in zip(['naive', 'robust'], all_train_stats):
      for idx, (mu, cov) in enumerate(stat):
        spectrum = np.linalg.eigvals(cov)
        path_to_csv = os.path.join(os.path.dirname(args.log_path), 'spectrum.csv')
        with open(path_to_csv, 'a') as f:
          wr = csv.writer(f)
          wr.writerow([name, max(spectrum), min(spectrum)])
        kappa = max(spectrum) / min(spectrum)
        plt.matshow(cov)
        plt.title(f"Cond.:{kappa:.3e} Max:{max(spectrum):.3e} Min: {min(spectrum):.3e}")
        cb = plt.colorbar()
        cb.ax.tick_params(labelsize=14)
        plt.savefig(os.path.join(os.path.dirname(args.log_path), f"{name}-cls{idx}.png"))
    exit()

  for s in range(args.start_seed, args.end_seed+1):
    logger.set_seed(s)
    loader = AttackLoader(args, logger, data_type=args.data_type)
    detector = Detector(model_wrapper, all_train_stats, loader, logger, params, (scaler, reducer, all_estimators, args.cov_estimator), use_val=args.use_val , dataset=args.dataset , seed=s)
    if args.baseline:
      detector.test_baseline_PPL(args.fpr_threshold)
    else:
      roc, auc, tpr_at_fpr, conf, testset = detector.test(args.fpr_threshold, args.pkl_test_path)

