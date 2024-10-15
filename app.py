import json
import logging
import uuid
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from decimal import Decimal
from flask import render_template

@app.route('/')
def index():
    return render_template('index.html')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('innovation-dashboard-IdeasTable-S1IG7A6P79OV')
bedrock = boto3.client('bedrock-runtime')

def lambda_handler(event, context):
    # Check if it's an OPTIONS request
    if event['httpMethod'] == 'OPTIONS':
        return handle_options_request()
    
    # Handle other HTTP methods (GET, POST, etc.)
    if event['httpMethod'] == 'GET':
        return get_ideas(event, context)
    elif event['httpMethod'] == 'POST':
        return submit_idea(event, context)
    else:
        return {
            'statusCode': 405,
            'body': json.dumps('Method Not Allowed')
        }

def handle_options_request():
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            #'Access-Control-Allow-Origin': 'https://f8c1210db6dd4ec2919fd33c315ff332.vfs.cloud9.us-east-1.amazonaws.com',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
            'Access-Control-Allow-Credentials': 'true'
        },
        'body': json.dumps('OK')
    }

def get_user_from_event(event):
    return event['requestContext']['authorizer']['claims']['email']
    
def get_existing_ideas():
    try:
        response = table.scan(
            ProjectionExpression="id, idea"
        )
        return response['Items']
    except ClientError as e:
        logger.error(f"Couldn't get existing ideas: {e}")
        return []

def submit_idea(event, context):
    logger.info(f"Received event in submit_idea: {json.dumps(event)}")
    
    # Define CORS headers
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        'Access-Control-Allow-Credentials': 'true'
    }
    
    try:
        # Log the entire event
        logger.info(f"Full event: {json.dumps(event)}")
        
        # Check if body exists and log it
        if 'body' in event:
            logger.info(f"Raw body: {event['body']}")
            try:
                body = json.loads(event['body'])
                logger.info(f"Parsed body: {json.dumps(body)}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse body as JSON: {str(e)}")
                return {
                    'statusCode': 400,
                    'headers': cors_headers,
                    'body': json.dumps({'error': 'Invalid JSON in request body'})
                }
        else:
            logger.error("No body found in the event")
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No body found in the request'})
            }

        # Check if idea exists in the body
        if 'idea' not in body:
            logger.error("No idea found in the body")
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No idea provided'})
            }
        
        new_idea = body['idea']
        logger.info(f"Received new idea: {new_idea}")
        
        # Fetch existing ideas
        existing_ideas = get_existing_ideas()
        logger.info(f"Fetched {len(existing_ideas)} existing ideas")

        # Check for duplicates
        duplicate_result = is_duplicate(new_idea, existing_ideas)
        logger.info(f"Duplicate check result: {duplicate_result}")

        # Generate a unique ID for the idea
        idea_id = str(uuid.uuid4())
        
        # Generate summary using Bedrock
        summary = generate_summary(new_idea)
        
        # Prepare the item to be saved in DynamoDB
        item = {
            'id': idea_id,
            'idea': new_idea,
            'votes': 0,
            'summary': summary,
            'comments': []
        }

        if duplicate_result['is_duplicate']:
            logger.info(f"Duplicate idea detected: {duplicate_result['similar_idea']}")
            item['duplicate_of'] = duplicate_result['similar_idea']
        else:
            logger.info("Unique idea detected")

        # Put the item in DynamoDB
        try:
            table.put_item(Item=item)
            logger.info(f"Idea saved to DynamoDB: {item}")
        except ClientError as e:
            logger.error(f"Couldn't put item in DynamoDB: {e}")
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Failed to save idea'})
            }
        
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'Idea submitted successfully',
                'id': idea_id,
                'duplicate': duplicate_result['is_duplicate'],
                'duplicate_of': duplicate_result['similar_idea'] if duplicate_result['is_duplicate'] else None
            })
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {str(e)}")
        return {
            'statusCode': 400,
            'headers': cors_headers,
            'body': json.dumps({'error': 'Invalid JSON in request body'})
        }
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': 'Internal server error'})
        }

# Helper function to convert Decimal to float
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def get_ideas(event, context):
    try:
        response = table.scan()
        ideas = response['Items']
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                #'Access-Control-Allow-Origin': 'https://f8c1210db6dd4ec2919fd33c315ff332.vfs.cloud9.us-east-1.amazonaws.com',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
                'Access-Control-Allow-Credentials': 'true'
            },
            'body': json.dumps(ideas, default=decimal_default)
        }
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': 'https://f8c1210db6dd4ec2919fd33c315ff332.vfs.cloud9.us-east-1.amazonaws.com',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'OPTIONS,GET',
                'Access-Control-Allow-Credentials': True,
            },
            'body': json.dumps({'error': str(e)})
        }
    
def vote_idea(event, context):
    idea_id = event['pathParameters']['id']
    
    response = table.update_item(
        Key={'id': idea_id},
        UpdateExpression='ADD votes :inc',
        ExpressionAttributeValues={':inc': 1},
        ReturnValues='UPDATED_NEW'
    )
    
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            #'Access-Control-Allow-Origin': 'https://f8c1210db6dd4ec2919fd33c315ff332.vfs.cloud9.us-east-1.amazonaws.com',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
            'Access-Control-Allow-Credentials': 'true'
        },
        'body': json.dumps('Vote recorded')
    }

def comment_idea(event, context):
    idea_id = event['pathParameters']['id']
    body = json.loads(event['body'])
    comment = body['comment']
    
    response = table.update_item(
        Key={'id': idea_id},
        UpdateExpression='SET comments = list_append(if_not_exists(comments, :empty_list), :comment)',
        ExpressionAttributeValues={
            ':comment': [comment],
            ':empty_list': []
        },
        ReturnValues='UPDATED_NEW'
    )
    
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            #'Access-Control-Allow-Origin': 'https://f8c1210db6dd4ec2919fd33c315ff332.vfs.cloud9.us-east-1.amazonaws.com',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
            'Access-Control-Allow-Credentials': 'true'
        },
        'body': json.dumps('Comment added')
    }

"""def get_all_ideas():
    response = table.scan()
    return response['Items']"""

def is_duplicate(new_idea, existing_ideas):
    try:
        if not existing_ideas:
            logger.info("No existing ideas to compare against")
            return {"is_duplicate": False, "similar_idea": None}

        prompt = f"""Human: Compare the following new idea with the list of existing ideas. Determine if the new idea is semantically similar or a duplicate of any existing idea.

New idea: "{new_idea}"

Existing ideas:
{json.dumps(existing_ideas, indent=2)}

Instructions:
1. Analyze the core concept of the new idea.
2. Compare this core concept to each existing idea.
3. Consider ideas as duplicates if they share the same fundamental concept or goal, even if the wording is different.
4. Ignore minor differences in phrasing or specific details if the main idea is the same.
5. If the new idea is a subset or superset of an existing idea, consider it a duplicate.

If the new idea is a duplicate or very similar to any existing idea, respond with:
DUPLICATE: <id of the most similar existing idea>

If the new idea is unique, respond with:
UNIQUE

Provide only one of these responses without any additional explanation.\n\nAssistant:"""

        response = bedrock.invoke_model(
            modelId='anthropic.claude-v2',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                "prompt": prompt,
                "max_tokens_to_sample": 100,
                "temperature": 0,
                "top_p": 1,
            })
        )

        result = json.loads(response['body'].read())
        output = result['completion'].strip()
        logger.info(f"Duplicate check output: {output}")

        if output.startswith("DUPLICATE:"):
            similar_idea_id = output.split(":")[1].strip()
            return {"is_duplicate": True, "similar_idea": similar_idea_id}
        elif output == "UNIQUE":
            return {"is_duplicate": False, "similar_idea": None}
        else:
            logger.error(f"Unexpected response from Bedrock: {output}")
            return {"is_duplicate": False, "similar_idea": None}

    except KeyError as e:
        logger.error(f"Unexpected response structure from Bedrock: {e}")
        return {"is_duplicate": False, "similar_idea": None}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON response from Bedrock: {e}")
        return {"is_duplicate": False, "similar_idea": None}
    except Exception as e:
        logger.error(f"Error checking for duplicates: {str(e)}")

def generate_summary(idea):
    try:
        # Format the prompt correctly for Claude
        prompt = f"\n\nHuman: Summarize the following idea in one sentence: '{idea}'\n\nAssistant:"
        
        response = bedrock.invoke_model(
            modelId='anthropic.claude-v2',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                "prompt": prompt,
                "max_tokens_to_sample": 100,
                "temperature": 0.7,
                "top_p": 1,
            })
        )
        
        result = json.loads(response['body'].read())
        summary = result['completion'].strip()
        logger.info(f"Generated summary: {summary}")
        return summary
    except KeyError as e:
        logger.error(f"Unexpected response structure from Bedrock: {e}")
        return "Error: Unable to generate summary"
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON response from Bedrock: {e}")
        return "Error: Unable to parse summary"
    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}")
        return "Error: Unable to generate summary"
