import os
import sys

from src.exception.exception import NetworkSecurityException 
from src.logging.logger import logging

from src.entity.artifact_entity import DataTransformationArtifact,ModelTrainerArtifact
from src.entity.config_entity import ModelTrainerConfig



from src.utils.ml_utils.model.estimator import NetworkModel
from src.utils.main_utils.utils import save_object,load_object
from src.utils.main_utils.utils import load_numpy_array_data,evaluate_models
from src.utils.ml_utils.metric.classification_metric import get_classification_score

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import r2_score
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import (
    AdaBoostClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier,
)
import mlflow
from urllib.parse import urlparse

import dagshub
dagshub.init(repo_owner='surajgrao0203', repo_name='Network_Security', mlflow=True)

from dotenv import load_dotenv
load_dotenv()



os.environ["MLFLOW_TRACKING_URI"]="https://dagshub.com/surajgrao0203/Network_Security.mlflow"
os.environ["MLFLOW_TRACKING_USERNAME"]="surajgrao0203"
os.environ["MLFLOW_TRACKING_PASSWORD"]="3392ea3f10ea49bc5fc14e0b7858a9386ee7341c"





class ModelTrainer:
    def __init__(self,model_trainer_config:ModelTrainerConfig,data_transformation_artifact:DataTransformationArtifact):
        try:
            self.model_trainer_config=model_trainer_config
            self.data_transformation_artifact=data_transformation_artifact
        except Exception as e:
            raise NetworkSecurityException(e,sys)
        
    def track_mlflow(self,best_model,classificationmetric):
        mlflow.set_registry_uri("https://dagshub.com/surajgrao0203/Network_Security.mlflow")
        tracking_url_type_store = urlparse(mlflow.get_tracking_uri()).scheme
        with mlflow.start_run():
            f1_score=classificationmetric.f1_score
            precision_score=classificationmetric.precision_score
            recall_score=classificationmetric.recall_score

            

            mlflow.log_metric("f1_score",f1_score)
            mlflow.log_metric("precision",precision_score)
            mlflow.log_metric("recall_score",recall_score)
            mlflow.sklearn.log_model(best_model,"model")
            # Model registry does not work with file store
            if tracking_url_type_store != "file":

                # Register the model
                # There are other ways to use the Model Registry, which depends on the use case,
                # please refer to the doc for more information:
                # https://mlflow.org/docs/latest/model-registry.html#api-workflow
                mlflow.sklearn.log_model(best_model, "model", registered_model_name=best_model)
            else:
                mlflow.sklearn.log_model(best_model, "model")


        
    def train_model(self,X_train,y_train,x_test,y_test):
        models = {
                "Random Forest": RandomForestClassifier(verbose=1),
                "Decision Tree": DecisionTreeClassifier(),
                "Gradient Boosting": GradientBoostingClassifier(verbose=1),
                "Logistic Regression": LogisticRegression(verbose=1),
                "AdaBoost": AdaBoostClassifier(),
            }
        params={
            "Decision Tree": {
                'criterion':['gini', 'entropy', 'log_loss'],
                # 'splitter':['best','random'],
                # 'max_features':['sqrt','log2'],
            },
            "Random Forest":{
                # 'criterion':['gini', 'entropy', 'log_loss'],
                
                # 'max_features':['sqrt','log2',None],
                'n_estimators': [8,16,32,128,256]
            },
            "Gradient Boosting":{
                # 'loss':['log_loss', 'exponential'],
                'learning_rate':[.1,.01,.05,.001],
                'subsample':[0.6,0.7,0.75,0.85,0.9],
                # 'criterion':['squared_error', 'friedman_mse'],
                # 'max_features':['auto','sqrt','log2'],
                'n_estimators': [8,16,32,64,128,256]
            },
            "Logistic Regression":{},
            "AdaBoost":{
                'learning_rate':[.1,.01,.001],
                'n_estimators': [8,16,32,64,128,256]
            }
            
        }
        model_report:dict=evaluate_models(X_train=X_train,y_train=y_train,X_test=x_test,y_test=y_test,
                                          models=models,param=params)
        
        ## To get best model score from dict
        best_model_score = max(sorted(model_report.values()))

        ## To get best model name from dict

        best_model_name = list(model_report.keys())[
            list(model_report.values()).index(best_model_score)
        ]
        best_model = models[best_model_name]
        y_train_pred=best_model.predict(X_train)

        classification_train_metric=get_classification_score(y_true=y_train,y_pred=y_train_pred)
        
        ## Track the experiements with mlflow
        self.track_mlflow(best_model,classification_train_metric)


        y_test_pred=best_model.predict(x_test)
        classification_test_metric=get_classification_score(y_true=y_test,y_pred=y_test_pred)

        self.track_mlflow(best_model,classification_test_metric)

        preprocessor = load_object(file_path=self.data_transformation_artifact.transformed_object_file_path)
            
        model_dir_path = os.path.dirname(self.model_trainer_config.trained_model_file_path)
        os.makedirs(model_dir_path,exist_ok=True)

        Network_Model=NetworkModel(preprocessor=preprocessor,model=best_model)
        save_object(self.model_trainer_config.trained_model_file_path,obj=NetworkModel)
        #model pusher
        save_object("final_model/model.pkl",best_model)
        

        ## Model Trainer Artifact
        model_trainer_artifact=ModelTrainerArtifact(trained_model_file_path=self.model_trainer_config.trained_model_file_path,
                             train_metric_artifact=classification_train_metric,
                             test_metric_artifact=classification_test_metric
                             )
        logging.info(f"Model trainer artifact: {model_trainer_artifact}")
        return model_trainer_artifact


    
    
        
    def initiate_model_trainer(self)->ModelTrainerArtifact:
        try:
            train_file_path = self.data_transformation_artifact.transformed_train_file_path
            test_file_path = self.data_transformation_artifact.transformed_test_file_path

            #loading training array and testing array
            train_arr = load_numpy_array_data(train_file_path)
            test_arr = load_numpy_array_data(test_file_path)

            x_train, y_train, x_test, y_test = (
                train_arr[:, :-1],
                train_arr[:, -1],
                test_arr[:, :-1],
                test_arr[:, -1],
            )

            model_trainer_artifact=self.train_model(x_train,y_train,x_test,y_test)
            return model_trainer_artifact

            
        except Exception as e:
            raise NetworkSecurityException(e,sys)
# import os
# import sys
# from urllib.parse import urlparse
# from dotenv import load_dotenv

# from src.exception.exception import NetworkSecurityException
# from src.logging.logger import logging
# from src.entity.artifact_entity import DataTransformationArtifact, ModelTrainerArtifact
# from src.entity.config_entity import ModelTrainerConfig
# from src.utils.ml_utils.model.estimator import NetworkModel
# from src.utils.main_utils.utils import save_object, load_object, load_numpy_array_data, evaluate_models
# from src.utils.ml_utils.metric.classification_metric import get_classification_score

# from sklearn.linear_model import LogisticRegression
# from sklearn.metrics import r2_score
# from sklearn.neighbors import KNeighborsClassifier
# from sklearn.tree import DecisionTreeClassifier
# from sklearn.ensemble import (
#     AdaBoostClassifier,
#     GradientBoostingClassifier,
#     RandomForestClassifier,
# )
# import mlflow
# import dagshub

# # Initialize Dagshub
# dagshub.init(repo_owner="surajgrao0203", repo_name="Network_Security", mlflow=True)

# # Load environment variables
# load_dotenv()

# # Set MLflow environment variables
# os.environ["MLFLOW_TRACKING_URI"] = "https://dagshub.com/surajgrao0203/Network_Security.mlflow"
# os.environ["MLFLOW_TRACKING_USERNAME"] = "surajgrao0203"
# os.environ["MLFLOW_TRACKING_PASSWORD"] = "3392ea3f10ea49bc5fc14e0b7858a9386ee7341c"


# class ModelTrainer:
#     def __init__(self, model_trainer_config: ModelTrainerConfig, data_transformation_artifact: DataTransformationArtifact):
#         try:
#             self.model_trainer_config = model_trainer_config
#             self.data_transformation_artifact = data_transformation_artifact
#         except Exception as e:
#             raise NetworkSecurityException(e, sys)

#     def track_mlflow(self, best_model, classification_metric):
#         """
#         Logs metrics and the model to MLflow.
#         """
#         try:
#             mlflow.set_registry_uri("https://dagshub.com/surajgrao0203/Network_Security.mlflow")
#             tracking_url_type_store = urlparse(mlflow.get_tracking_uri()).scheme

#             with mlflow.start_run():
#                 # Log metrics
#                 mlflow.log_metric("f1_score", classification_metric.f1_score)
#                 mlflow.log_metric("precision", classification_metric.precision_score)
#                 mlflow.log_metric("recall", classification_metric.recall_score)

#                 # Register the model
#                 model_name = "Best_Classification_Model"  # Specify a meaningful name
#                 if tracking_url_type_store != "file":
#                     mlflow.sklearn.log_model(best_model, "model", registered_model_name=model_name)
#                 else:
#                     mlflow.sklearn.log_model(best_model, "model")

#         except Exception as e:
#             raise NetworkSecurityException(e, sys)

#     def train_model(self, X_train, y_train, X_test, y_test):
#         """
#         Trains multiple models and selects the best one based on evaluation metrics.
#         """
#         try:
#             # Define models and hyperparameters
#             models = {
#                 "Random Forest": RandomForestClassifier(verbose=1),
#                 "Decision Tree": DecisionTreeClassifier(),
#                 "Gradient Boosting": GradientBoostingClassifier(verbose=1),
#                 "Logistic Regression": LogisticRegression(verbose=1),
#                 "AdaBoost": AdaBoostClassifier(),
#             }
#             params = {
#                 "Decision Tree": {
#                     'criterion': ['gini', 'entropy', 'log_loss'],
#                 },
#                 "Random Forest": {
#                     'n_estimators': [8, 16, 32, 128, 256],
#                 },
#                 "Gradient Boosting": {
#                     'learning_rate': [0.1, 0.01, 0.05, 0.001],
#                     'subsample': [0.6, 0.7, 0.75, 0.85, 0.9],
#                     'n_estimators': [8, 16, 32, 64, 128, 256],
#                 },
#                 "Logistic Regression": {},
#                 "AdaBoost": {
#                     'learning_rate': [0.1, 0.01, 0.001],
#                     'n_estimators': [8, 16, 32, 64, 128, 256],
#                 },
#             }

#             # Evaluate models
#             model_report: dict = evaluate_models(
#                 X_train=X_train, y_train=y_train, X_test=X_test, y_test=y_test,
#                 models=models, param=params
#             )

#             # Select the best model
#             best_model_score = max(sorted(model_report.values()))
#             best_model_name = list(model_report.keys())[list(model_report.values()).index(best_model_score)]
#             best_model = models[best_model_name]

#             # Evaluate model on training and testing data
#             y_train_pred = best_model.predict(X_train)
#             classification_train_metric = get_classification_score(y_true=y_train, y_pred=y_train_pred)

#             # Track experiment in MLflow
#             self.track_mlflow(best_model, classification_train_metric)

#             y_test_pred = best_model.predict(X_test)
#             classification_test_metric = get_classification_score(y_true=y_test, y_pred=y_test_pred)
#             self.track_mlflow(best_model, classification_test_metric)

#             # Save the trained model
#             preprocessor = load_object(file_path=self.data_transformation_artifact.transformed_object_file_path)
#             model_dir_path = os.path.dirname(self.model_trainer_config.trained_model_file_path)
#             os.makedirs(model_dir_path, exist_ok=True)

#             network_model = NetworkModel(preprocessor=preprocessor, model=best_model)
#             save_object(self.model_trainer_config.trained_model_file_path, obj=network_model)
#             save_object("final_model/model.pkl", best_model)

#             # Return model trainer artifact
#             return ModelTrainerArtifact(
#                 trained_model_file_path=self.model_trainer_config.trained_model_file_path,
#                 train_metric_artifact=classification_train_metric,
#                 test_metric_artifact=classification_test_metric
#             )

#         except Exception as e:
#             raise NetworkSecurityException(e, sys)

#     def initiate_model_trainer(self) -> ModelTrainerArtifact:
#         """
#         Initializes the model training pipeline.
#         """
#         try:
#             # Load transformed data
#             train_file_path = self.data_transformation_artifact.transformed_train_file_path
#             test_file_path = self.data_transformation_artifact.transformed_test_file_path

#             train_arr = load_numpy_array_data(train_file_path)
#             test_arr = load_numpy_array_data(test_file_path)

#             X_train, y_train, X_test, y_test = (
#                 train_arr[:, :-1],
#                 train_arr[:, -1],
#                 test_arr[:, :-1],
#                 test_arr[:, -1],
#             )

#             # Train the model and return the artifact
#             return self.train_model(X_train, y_train, X_test, y_test)

#         except Exception as e:
#             raise NetworkSecurityException(e, sys)