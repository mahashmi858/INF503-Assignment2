import math
import os
import pdb
import pickle
import random
import re

from tqdm import tqdm

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import GPT2LMHeadModel, GPT2TokenizerFast

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import roc_curve, precision_recall_curve, precision_recall_fscore_support, auc
from sklearn.covariance import LedoitWolf, MinCovDet, GraphicalLasso, OAS

from utils.miscellaneous import save_pkl, load_pkl, return_cov_estimator


# Forward using train data to get empirical mean and covariance
def get_stats(features, labels, cov_estim_name=None, use_shared_cov=False, params=None):
  # Compute mean and covariance of each cls.
  stats = []
  estimators = []
  label_list = range(len(np.unique(labels)))

  if use_shared_cov:
    shared_cov = None
    shared_feat = []

    for idx, lab in enumerate(label_list):
      feat = features[labels==lab]
      shared_feat.append(feat)
      feat = feat
      mu = feat.mean(axis=0)
      stats.append([mu, 0])

    shared_feat = np.concatenate(shared_feat)
    shared_cov = np.cov(shared_feat, rowvar=False)

    for idx, lab in enumerate(label_list):
      stats[idx][1] = shared_cov

    return stats

  # Estimate covariance per class
  else:
    for idx, lab in enumerate(label_list):
      cov_estim = return_cov_estimator(cov_estim_name, params)
      feat = features[labels==lab]
      mu = feat.mean(axis=0)
      if cov_estim:
        cov = cov_estim.fit(feat).covariance_
        estimators.append(cov_estim)
      else:
        cov = np.cov(feat, rowvar=False)
      stats.append([mu, cov])
  return stats, estimators


def get_train_features(model_wrapper, args, batch_size, dataset, text_key, layer=-1):
  assert layer=='pooled' or layer < 0 , "Layer either has to be a int between -12~-1 or the pooling layer"
  model_name = os.path.basename(args.target_model)
  model_name += f"-layer_{layer}"

  if os.path.exists(f"saved_feats/{model_name}.pkl"):
    features = load_pkl(f"saved_feats/{model_name}.pkl")
    feats_tensor = []
    for cls, x in enumerate(features):
      data = torch.cat(x, dim=0)
      cls_vector = torch.tensor(cls).repeat(data.shape[0], 1)
      feats_tensor.append(torch.cat([data, cls_vector], dim=1))

    feats_tensor = torch.cat(feats_tensor, dim=0)
    return feats_tensor

  print("Building train features")
  model = model_wrapper.model
  num_samples = len(dataset['label'])
  label_list = np.unique(dataset['label'])
  num_labels = len(label_list)
  num_batches = int((num_samples // batch_size) + 1)
  features = [[] for _ in range(num_labels)]

  with torch.no_grad():
    for i in tqdm(range(num_batches)):
      lower = i * batch_size
      upper = min((i + 1) * batch_size, num_samples)
      examples = dataset[text_key][lower:upper]
      labels = dataset['label'][lower:upper]
      y = torch.LongTensor(labels)
      output = model_wrapper.inference(examples, output_hs=True)
      preds = output.logits
      if type(layer) == int:
        feat = output.hidden_states[layer][:, 0, :].cpu()  # (Batch_size, 768)
        for idx, lab in enumerate(label_list):
          features[idx].append(feat[y == lab])
      elif layer == 'pooled':
        feat = output.hidden_states[-1]  # (Batch_size, 768)
        pooled_feat = model.bert.pooler(feat).cpu()
        for idx, lab in enumerate(label_list):
          features[idx].append(pooled_feat[y==lab])

  if not os.path.exists("saved_feats/"):
    os.mkdir('saved_feats')
  save_pkl(features, f"saved_feats/{model_name}.pkl")

  feats_tensor = []
  for cls, x in enumerate(features):
    data = torch.cat(x, dim=0)
    cls_vector = torch.tensor(cls).repeat(data.shape[0], 1)
    feats_tensor.append(torch.cat([data, cls_vector], dim=1))
  feats_tensor = torch.cat(feats_tensor, dim=0)

  return feats_tensor


def get_test_features(model_wrapper, batch_size, dataset, params, logger=None):
  # dataset, batch_size, i, layer = testset['text'].tolist(), 32, 0, -1
  assert logger is not None, "No logger given"
  num_samples = len(dataset)
  num_batches = int((num_samples // batch_size) + 1)
  features = []
  preds = []
  layer = params['layer_param']['cls_layer']

  with torch.no_grad():
    for i in tqdm(range(num_batches)):
      lower = i * batch_size
      upper = min((i + 1) * batch_size, num_samples)
      examples = dataset[lower:upper]
      if len(examples) == 0:
        continue
      output = model_wrapper.inference(examples, output_hs=True, output_attention=True)
      _, pred = torch.max(output.logits, dim=1)
      feat = output.hidden_states[layer][:, 0,:].cpu()  # output.hidden_states : (Batch_size, sequence_length, hidden_dim)
      features.append(feat.cpu())
      preds.append(pred.cpu())
  return torch.cat(features, dim=0), torch.cat(preds, dim=0)

def compute_dist(test_features, train_stats, diagonal_cov=False, regularized_cov=False, use_marginal=True):
  # stats is list of np.array ; change to torch operations for gradient update
  output = []
  raw_score = []
  for (mu, cov) in train_stats:
    mu, cov = torch.tensor(mu).double(), torch.tensor(cov).double()
    if diagonal_cov:
      diag_cov = torch.diag(cov)
      cov = torch.diag(diag_cov)
    if regularized_cov:
      weight = torch.diag(cov).mean()
      weight = 1
      cov = cov + weight * torch.diag(torch.ones(cov.shape[0]))
    prec = torch.inverse(cov)
    delta = test_features-mu
    neg_dist = - torch.einsum('nj, jk, nk -> n', delta, prec, delta)
    log_likelihood = (0.5 * neg_dist) + math.log((2 * math.pi) ** (-mu.shape[0] / 2))
    output.append(log_likelihood.unsqueeze(-1))
    raw_score.append(neg_dist.unsqueeze(-1))

  output = torch.cat(output, dim=-1)
  raw_score = torch.cat(raw_score, dim=-1)
  confidence, conf_indices = torch.max(output, dim=1) #Takes the max of class conditional probability
  if use_marginal:
    # confidence = torch.log(torch.sum(torch.exp(output), dim=1)) # Takes the marginal probability
    score = torch.sum(raw_score, dim=-1)
    return score, conf_indices, output
  return confidence, conf_indices, output


def detect_attack(testset, confidence, fpr_thres=0.05, visualize=False, logger=None, mode=None,
                  log_metric=False):
  """
  Detect attack for correct samples only to compute detection metric (TPR, recall, precision)
  """
  assert logger is not None, "Logger not given"
  target = np.array(testset['result_type'].tolist())
  conf = confidence.numpy()
  testset['negative_conf'] = -conf # negative of confidence : likelihood of adv. probability

  """
  target \in {0,1} ; 0 : normal, 1: adv. samples 
  Higher negative confidence indicates higher likelihood of adversarial samples 
  """
  fpr, tpr, thres1 = roc_curve(target, -conf)
  precision, recall, thres2 = precision_recall_curve(target, -conf)
  mask = (fpr <= fpr_thres)
  tpr_at_fpr = np.max(tpr * mask) # Maximum tpr at fpr <= fpr_thres
  roc_cutoff = np.sort(np.unique(mask*thres1))[1]
  pred = np.zeros_like(conf)
  pred[-conf>=roc_cutoff] = 1
  prec, rec, f1, _ = precision_recall_fscore_support(target, pred, average='binary')
  auc_value = auc(fpr, tpr)
  logger.log.info(f"TPR at FPR={fpr_thres} : {tpr_at_fpr:.3f}")
  logger.log.info(f"F1 : {f1:.3f}, prec: {prec:.3f}, recall: {rec:.3f}")
  logger.log.info(f"AUC: {auc_value:.3f}")
  if visualize:
    fig, ax = plt.subplots()
    kwargs = dict(histtype='stepfilled', alpha=0.3, bins=50, density=False)
    x1 = testset.loc[testset.result_type==0, ['negative_conf']].values.squeeze()
    ax.hist(x=x1, label='clean', **kwargs)
    x2 = testset.loc[testset.result_type==1, ['negative_conf']].values.squeeze()
    ax.hist(x=x2, label='adv', **kwargs)
    ax.annotate(f'{int(roc_cutoff)}', xy=(roc_cutoff,0), xytext=(roc_cutoff,30), fontsize=14,
                arrowprops=dict(facecolor='black', width=1, shrink=0.1, headwidth=3))
    ax.legend()
    fig.savefig(os.path.join(logger.log_path, f"{mode}-hist.png"))

  if log_metric:
    metrics = {"tpr":tpr_at_fpr, "fpr":fpr_thres, "f1":f1, "auc":auc_value}
    logger.log_metric(metrics)

  metric1 = (fpr, tpr, thres1)
  metric2 = (precision, recall, thres2)
  return metric1, metric2, tpr_at_fpr, f1, auc_value


def compute_ppl(texts):
  MODEL_ID = 'gpt2-large'
  print(f"Initializing {MODEL_ID}")
  model = GPT2LMHeadModel.from_pretrained(MODEL_ID).cuda()
  model.eval()
  tokenizer = GPT2TokenizerFast.from_pretrained(MODEL_ID)
  encodings = tokenizer.batch_encode_plus(texts, add_special_tokens=True, truncation=True)

  batch_size = 1
  num_batch = len(texts) // batch_size
  eval_loss = 0
  likelihoods = []

  with torch.no_grad():
    for i in range(num_batch):
      start_idx = i * batch_size;
      end_idx = (i + 1) * batch_size
      x = encodings[start_idx:end_idx]
      ids = torch.LongTensor(x[0].ids)
      ids = ids.cuda()
      nll = model(input_ids=ids, labels=ids)[0] # negative log-likelihood
      likelihoods.append(-1 * nll.item())

  return torch.tensor(likelihoods)