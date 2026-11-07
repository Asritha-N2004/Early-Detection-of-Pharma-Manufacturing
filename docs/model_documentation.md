# Model lifecycle and interpretation

## Anomaly screening

The platform provides Isolation Forest, novelty Local Outlier Factor, One-Class SVM, Z-score, rolling statistical limits, EWMA, CUSUM and a small MLP reconstruction autoencoder. Their bounded indicators can be compared and averaged. Engineering-range excursions independently flag potential findings. Multivariate screening uses standardized shrinkage covariance distance and an Isolation Forest indicator. These scores are **not** deviation probabilities.

Demo mode can fit per-batch historical references for exploration. Training also creates a versioned `anomaly_ensemble` artifact from labeled-normal training batches, including all fitted detectors, approved-range snapshots, covariance reference and thresholds. Once approved and activated, inference loads this frozen artifact rather than refitting. An operating-range signature mismatch fails safely and requires a reviewed replacement version. Controlled mode requires both an approved active predictor and an approved active anomaly artifact for that process.

## Predictors and uncertainty

Random Forest, Gradient Boosting and XGBoost predict the next observed sample's excursion label within each batch. Process schemas are not mixed. Incomplete windows are excluded, and batches with insufficient aligned labeled samples are not used. Earlier batches train, the penultimate batch calibrates, and the last batch tests. Training and validation targets that cross the next split boundary are purged, protecting against overlapping-batch temporal leakage.

Sigmoid calibration is fitted on the validation batch only when both classes are present. The final test batch reports precision, recall, F1, ROC-AUC/PR-AUC where defined, false-positive/negative rates, Brier score, calibration bins, batch confusion counts and contiguous-event timing. Undefined metrics remain null. Event lead time searches only prior labeled-normal observations within fifteen minutes; missed detections are explicit, not invented zero latency.

Minute-based trend forecasts are separate from classifier predictions. Slopes use actual elapsed time, and calibration windows never join different training batches. They extrapolate recent slopes using actual observed cadence and provide a within-batch, time-horizon rolling-origin residual envelope when enough horizon-specific residuals exist. This empirical envelope has no guaranteed coverage under time dependence or drift. When insufficient history exists, uncertainty is explicitly unavailable.

## Governance, explanations and drift

Registry entries preserve dataset hashes, chronological batch identities, metrics, artifact SHA-256, training actor/date, task, version, approval and activation history. Approval and activation are distinct audited actions. Only one model per process/task is active. Legacy artifacts without integrity metadata must be retrained. Trusted model paths and hashes are checked before loading; deserialization is never an upload feature. Immutable version caching reduces repeated loading without skipping per-request integrity checks.

TreeSHAP explains approved predictor outputs and held-out model behavior. Anomaly contributions use reference departure and detector comparisons. Neither is causal evidence. Rolling standardized feature-mean shifts compare online inputs to training reference using a configurable threshold. Drift and incomplete model inputs route findings for additional human assessment.

Synthetic labels are generated from engineering-range excursions. High range-rule performance therefore does not establish independent learned-model quality, real manufacturing validity or patient safety. Approval records are prototype administrative records, not regulated validation or electronic signatures. Independent realistic batches, adjudicated ground truth, calibrated instruments and quality procedures remain required before regulated use. Optional LSTM was not necessary for the prototype.

Model-training configuration controls seed, tree count/depth, contamination, SVM nu, autoencoder iterations and decision thresholds. It is audited and snapshotted into newly trained artifacts; changing it does not silently alter active approved predictors. Agent configuration also controls nominal forecast coverage and the UI default horizon.
