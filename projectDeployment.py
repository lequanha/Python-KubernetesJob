import os
import argparse
import json
import pymsteams
from dotenv import load_dotenv

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.ProjectObject import ProjectObject
from src.configurations import configurations
from src.helper_database import postLaunchUpdate, failedLaunchUpdate, postDeleteUpdate

load_dotenv()
ENV = os.environ.get('ENVIRONMENT', 'local')
conf = configurations[ENV]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        'This program creates a sample Project with all components configured with internal Postgres DB connections')
    parser.add_argument('projName', help='Name of the project')
    parser.add_argument('projId', help='ID of project in database')
    parser.add_argument('entId', help='ID of enterprise account')
    parser.add_argument('--clusterNamespace', help='Namespace where cluster is deployed', default='lequanha')
    parser.add_argument('--components', nargs='+', help='List of applications to launch', default=[])
    parser.add_argument('--members', help='JSON string of member names, password and role',
                        default='{"test@test.com":{"password":"test", "permission":"creator"}}')
    parser.add_argument('--clean', help='Remove project in its entirety', action='store_true')

    args = parser.parse_args()
    projName = args.projName
    projId = int(args.projId)
    entId = int(args.entId)
    clusterNamespace = args.clusterNamespace
    components = args.components
    members = args.members.replace("'", '"')
    members = json.loads(members)
    clean = args.clean

    postgresName = 'lequanha-pgdb-cluster'
    notifyTeams = pymsteams.connectorcard(os.environ['PYMSTEAMS_URL'])

    dbURL = os.environ.get('DB_IP')
    dbPassword = os.environ.get('DB_PASSWORD')
    dbPort = os.environ.get('DB_PORT')
    dbURI = f'postgresql://apioperator:{dbPassword}@{dbURL}:{dbPort}/pyk8s?sslmode=require'
    engine = create_engine(dbURI, echo=False)
    Session = sessionmaker(bind=engine)

    if not clean:  # Launch project
        try:
            proj = ProjectObject(projName, entId, members, components, clusterNamespace)
            proj.launchProject()
            session = Session()
            postLaunchUpdate(session, projId, proj.members, proj.applications)

        # If occur any exceptions. Clean all project remnants, update database and send notifications to MS Teams
        except Exception as err:
            if session:
                session.rollback()
                session.bind.dispose()
                session.close()

            proj.cleanProject()
            session = Session()
            failedLaunchUpdate(session, projId)

            notifyTeams.text(f'{conf.host} - Project Deployment: \n{str(err)}')
            notifyTeams.send()
            raise err

    else:  # Clean project
        try:
            proj = ProjectObject(projName, entId, members, components, clusterNamespace)
            proj.cleanProject(deleteJobName=f'project-deployment-{projId}-{projName}', raiseError=True)
            session = Session()
            postDeleteUpdate(session, projId)

        # If occur any exceptions. Update database and send notifications to MS Teams
        except Exception as err:
            if session:
                session.rollback()
                session.bind.dispose()
                session.close()

            session = Session()
            failedLaunchUpdate(session, projId, status='deleted')

            notifyTeams.text(f'{conf.host} - Project Deletion: \n{str(err)}')
            notifyTeams.send()
            raise err
