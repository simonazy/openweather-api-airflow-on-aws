from airflow import DAG
from datetime import timedelta, datetime
from airflow.providers.http.sensors.http import HttpSensor
import json
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.s3 import S3CreateObjectOperator
import pandas as pd

def kelvin_to_fahrenheit(temp_in_kelvin):
    temp_in_fahrenheit = (temp_in_kelvin - 273.15) * (9/5) + 32
    return temp_in_fahrenheit


def transform_load_data(task_instance):
    data = task_instance.xcom_pull(task_ids="extract_weather_data")
    city = data["name"]
    weather_description = data["weather"][0]['description']
    temp_farenheit = kelvin_to_fahrenheit(data["main"]["temp"])
    feels_like_farenheit= kelvin_to_fahrenheit(data["main"]["feels_like"])
    min_temp_farenheit = kelvin_to_fahrenheit(data["main"]["temp_min"])
    max_temp_farenheit = kelvin_to_fahrenheit(data["main"]["temp_max"])
    pressure = data["main"]["pressure"]
    humidity = data["main"]["humidity"]
    wind_speed = data["wind"]["speed"]
    time_of_record = datetime.utcfromtimestamp(data['dt'] + data['timezone'])
    sunrise_time = datetime.utcfromtimestamp(data['sys']['sunrise'] + data['timezone'])
    sunset_time = datetime.utcfromtimestamp(data['sys']['sunset'] + data['timezone'])

    transformed_data = {"City": city,
                        "Description": weather_description,
                        "Temperature (F)": temp_farenheit,
                        "Feels Like (F)": feels_like_farenheit,
                        "Minimun Temp (F)":min_temp_farenheit,
                        "Maximum Temp (F)": max_temp_farenheit,
                        "Pressure": pressure,
                        "Humidty": humidity,
                        "Wind Speed": wind_speed,
                        "Time of Record": time_of_record,
                        "Sunrise (Local Time)":sunrise_time,
                        "Sunset (Local Time)": sunset_time                        
                        }
    transformed_data_list = [transformed_data]
    df_data = pd.DataFrame(transformed_data_list)
    dt_string = 'current_weather_london_' + datetime.now().strftime("%d%m%Y%H%M%S")
    filename = f'weather_data/{dt_string}.csv'

    csv_string = df_data.to_csv(index=False)
    
    return csv_string, filename

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 8, 9),
    'email': ['myeamil@emailgmail.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=2)
}


with DAG('weather_dag',
        default_args=default_args,
        schedule_interval = '@daily',
        catchup=False) as dag:


        is_weather_api_ready = HttpSensor(
        task_id ='is_weather_api_ready',
        http_conn_id='weathermap_api',
        endpoint='/data/2.5/weather?q=London&appid=07bed7359a44acc9348cb19d1788284b'
        )


        extract_weather_data = SimpleHttpOperator(
        task_id = 'extract_weather_data',
        http_conn_id = 'weathermap_api',
        endpoint='/data/2.5/weather?q=London&appid=07bed7359a44acc9348cb19d1788284b',
        method = 'GET',
        response_filter= lambda r: json.loads(r.text),
        log_response=True
        )

        transform_load_weather_data = PythonOperator(
        task_id= 'transform_load_weather_data',
        python_callable=transform_load_data
        )

        upload_to_s3 = S3CreateObjectOperator(
        task_id='upload_to_s3',
        aws_conn_id='aws_default',  # Set up this connection in Airflow
        s3_bucket='my-openweaterapi-dailydata',
        s3_key="{{ task_instance.xcom_pull(task_ids='transform_load_weather_data')[1]}}",
        data="{{ task_instance.xcom_pull(task_ids='transform_load_weather_data')[0]}}",
        replace=True,
        encrypt=False)  # Set to True if you want server-side encryption


        is_weather_api_ready >> extract_weather_data >> transform_load_weather_data >> upload_to_s3