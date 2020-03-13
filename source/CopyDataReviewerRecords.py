# ---------------------------------------------------------------------------
# Created By: The ArcGIS Data Reviewer Team

# Copyright 2020 Esri

# Licensed under the Apache License, Version 2.0 (the "License"); You
# may not use this file except in compliance with the License. You may
# obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

# A copy of the license is available in the repository's
# LICENSE file.

# Description:
# Copies the records from the selected Reviewer Sessions that meet the optional
# SQL Expression into the chosen output Reviewer Workspace.  Output workspace
# can be the same as the input workspace. You have the option to create a
# logfile that records information about the imported records. You also have
# the option to delete the copied records from the input Reviewer Workspace.

# Disclaimer:
# Due to the complex relationship of tables within the Reviewer Workspace,
# modifying the content of this script is not recommended.  If you would like
# changes or enhancements to this script, please comment on the template
# through the Resource Center.

# Minimum ArcGIS Version: 10.6
# Last Modified: 11/27/2019
# ---------------------------------------------------------------------------

# Import necessary modules
import arcpy
import os
import datetime
import time
import sys
import uuid

from arcpy import env

#-------------------------------------
# get full path to tables - including qualified table name
# -----------------------------------
def getFullPath(in_workspace, table_name, no_exist_error=False):

    full_path = ''

    """In 10.6, the walk function does not return any tables if
    connecting to a SQL Express database as a database server.  However,
    it works when using a .sde connection.  This is a workaround"""
    if arcpy.Describe(in_workspace).workspaceType == 'RemoteDatabase' and not str(in_workspace).upper().endswith('.SDE'):
##        arcpy.AddMessage("list")
        arcpy.env.workspace = in_workspace

        # table_name will either be a stand-alone table
        # list the tables
        tables = arcpy.ListTables()
        for table in tables:
##            arcpy.AddMessage(table)
            #find the table that ends with the table name
            # this ignores table qualification and GDB_ name changes
            if table.upper().endswith(table_name.upper()):
                full_path  = os.path.join(in_workspace, table)
                break

        # if table_name does not exist, check to see if it is one of the
        # reviewer geometries in the REVDATASET
        if full_path == '':
            fds = arcpy.ListDatasets("*REVDATASET", "Feature")
            for fd in fds:
                fcs = arcpy.ListFeatureClasses("", "", fd)
                for fc in fcs:
                    if fc.endswith(table_name):
                        full_path  = os.path.join(in_workspace, fd, fc)
                        break

    else:
##        arcpy.AddMessage('walk')
        walk = arcpy.da.Walk(in_workspace)

        for dirpath, dirnames, filenames in walk:
            for name in filenames:
                if name.upper().endswith(table_name.upper()) :
                    full_path = (os.path.join(dirpath, name))
                    break

    # if the table cannot be found in the workspace
    if no_exist_error and (full_path == '' or not arcpy.Exists(full_path)):
            arcpy.AddError("Cannot find table {} in workspace {}.  Please ensure workspace is a valid Reviewer workspace.".format(table_name, in_workspace))
            sys.exit(0)

##    arcpy.AddMessage(full_path)
    return full_path

# ---------------------------------------------------------------------------
# This function determines if the version of the Reviewer Workspace
# ---------------------------------------------------------------------------
def DetermineVersion(RevWorkspace):
    version = 'Pre10.6'

    VERSIONTABLE = getFullPath(RevWorkspace, "REVWORKSPACEVERSION")

    # if the version table exists, the database is at least a 10.6 database
    if VERSIONTABLE != '' :
        schema_version = [row[0] for row in arcpy.da.SearchCursor(VERSIONTABLE, ['SCHEMAHASH'])]
        schema_version = set(schema_version)
        if len(schema_version) != 1:
            arcpy.AddWarning('Reviewer Version is inconsistent')

        if '{DDC860BD-4C40-302F-B5BE-3D0EDA623B6B}' in schema_version:
            version = '10.6'
        else:
            version = 'Unsupported'


    else:
        main_table = getFullPath(RevWorkspace, "REVTABLEMAIN", True)
        fields =[x.name.upper() for x in arcpy.ListFields(main_table)]
        if "LIFECYCLEPHASE" not in fields:
            version = 'Pre10.3'

##    arcpy.AddMessage('database {} is version {}'.format(RevWorkspace, version))
    return version


# ---------------------------------------------------------------------------
# This function determines if the Spatial Reference of Input and Output match
# ---------------------------------------------------------------------------
def CompareSR(InFeatures, OutFeatures):

    # Get the spatial reference name from the first feature class
    InDesc = arcpy.Describe(InFeatures)
    InSR = InDesc.spatialReference.name

    # Get the spatial reference name from the second feature class
    OutDesc = arcpy.Describe(OutFeatures)
    OutSR = OutDesc.spatialReference.name

    # Do the feature class names match?
    if InSR == OutSR:
        match = True
    else:
        match = False
        arcpy.AddWarning("Spatial reference of input and output Reveiwer workspaces do not match.  Reviewer geometries will be projected")
        arcpy.AddWarning("Input Spatial Reference: {}".format(InSR))
        arcpy.AddWarning("Output Spatial Reference: {}".format(OutSR))

    return match

# -----------------------------------------------------------
# This function is for writing lists of values to the logfile
# also gathers summary information about each dictionary
# -----------------------------------------------------------
def SummarizeDictionaries(logfile, matches, summarydict):

    if 'tableName' in matches:
        name = matches.pop('tableName')

    in_field_name = 'Input ID'
    out_field_name = 'Output ID'
    if "InIDField" in matches:
        in_field_name = matches.pop("InIDField")
    if "OutIDField" in matches:
        out_field_name = matches.pop("OutIDField")

    if len(matches) > 0:
        if logfile != '':
            logfile.write("\n{}...\n".format(name))
            logfile.write("   {} - {} \n".format(in_field_name, out_field_name))
            for InItem, OutItem in matches.items():
                logfile.write("    {} - {}\n".format(InItem, OutItem))

    summarydict[name] = str(len(matches))

    return summarydict

# ------------------------------------------------------------------------------
# Copies reviewer geometry features to the output reviewer workspace and session
# ------------------------------------------------------------------------------
def CopyGeometryFeatures(inFeatures, outFeatures, sessionWhereClause, idMap, outSessionID, matchDict):
    # determine fields from input feature class
    in_names =[x.name for x in arcpy.ListFields(inFeatures)]

    if "LINKID" in in_names:
        in_link_name = "LINKID"
    else:
        in_link_name = "LINKGUID"

    if 'BITMAP' in in_names:
        in_fields = ("OID@", in_link_name, 'BITMAP')
    else:
        in_fields = ("OID@", in_link_name, "SHAPE@")

##        arcpy.AddMessage(in_fields)

    # determine fields from output feature class
    out_names =[x.name for x in arcpy.ListFields(outFeatures)]
    if "LINKID" in out_names:
        out_link_name = "LINKID"
    else:
        out_link_name = "LINKGUID"

    if 'BITMAP' in out_names:
        out_fields = (out_link_name, "SESSIONID", 'BITMAP')
    else:
        out_fields = (out_link_name, "SESSIONID", "SHAPE@")

##        arcpy.AddMessage(out_fields)

    matchDict["InIDField"] = in_link_name
    matchDict["OutIDField"] = out_link_name

    # open insert cursor
    insert = arcpy.da.InsertCursor(outFeatures, out_fields)

    try:
        with arcpy.da.SearchCursor(inFeatures, in_fields, sessionWhereClause) as cursor:
            for row in cursor:
                # get linkID value for record
                linkID = row[1]
##                    arcpy.AddMessage(linkID)

                # if the link ID is in the idMap, then the record for this geometry
                # was ported to the target reviewer workspace
                if linkID in idMap:
                    outLinkID = idMap[linkID]
##                        arcpy.AddMessage(outLinkID)

                    # add new row to output feature class
                    new_row = [outLinkID, outSessionID, row[2]]
                    outID = insert.insertRow(new_row)

                    matchDict[linkID] = outLinkID
##                        inIDs.append(row[0])
##                        outIDs.append(outID)
    finally:
        del insert

# ---------------------------------------------------
# Makes a SQL IN clause from a list of values
# ---------------------------------------------------
def MakeInClause(inFC, intFieldName, inList):
    whereClause = None
    try:

        if len(inList) >= 1:
            # determine field type
            fields = arcpy.ListFields(inFC)
            field_type = None
            for field in fields:

                if field.name.upper() == intFieldName.upper():
                    field_type = field.type

            if field_type:
                csv = ""
                if field_type in ('Double', 'Integer', 'OID', 'Single', 'SmallInteger'):

                    for i in inList:
                        csv += "{0},".format(i)

                    # Remove trailing comma
                    csv = csv[:-1]
                elif field_type in ('Date', 'GlobalID', 'OID', 'Guid', 'String'):
                    for i in inList:
                        csv += "'{0}',".format(i)

                    # Remove trailing comma
                    csv = csv[:-1]
                else:
                    arcpy.AddWarning('Query field {} has an unsupported field type {}.  Query will not be created.'.format(intFieldName, field_type))

                if not csv == "":
                    whereClause = '{0} IN ({1})'.format(arcpy.AddFieldDelimiters(inFC, intFieldName), csv)
            else:
                arcpy.AddMessage("Cannot find field {} in {}.  Unable to create query.".format(intFieldName, inFC))
        else:
            arcpy.AddWarning("Unable to create query for field {}.  No values to query.".format(intFieldName))
    finally:
##        arcpy.AddMessage(whereClause)
        return whereClause

# ------------------------------------------------------------------
# Deletes rows from an input table/feature class given a list of IDs
# ------------------------------------------------------------------
def DeleteRows(inWorkspace, dictionary):
    del_count = 0
    dict_count = 0
    table = None    
    edit = arcpy.da.Editor(inWorkspace)
    #In Python 3, dict.keys() returns a dict_keys object (a view of the dictionary) which does not have remove method; 
    # unlike Python 2, where dict.keys() returns a list object.
    if arcpy.GetInstallInfo()['ProductName'] == 'Desktop':
        idList = dictionary.keys()
    else:
        idList = list(dictionary) 

    try:


        if 'tableName' in dictionary:
            table = dictionary['tableName']
            if "InIDField" in dictionary:
                field = dictionary['InIDField']
            else:
                field = 'OID@'

            if 'tableName' in idList:
                idList.remove('tableName')

            if "InIDField" in idList:
                idList.remove("InIDField")
            if "OutIDField" in idList:
                idList.remove("OutIDField")

            dict_cnt = len(idList)

            if table and len(idList) >= 1:
                table_path = getFullPath(inWorkspace, table)
                if table_path != '':

                    # Start an edit session
                    desc = arcpy.Describe(table_path)
                    if desc.canVersion == 1 and desc.isVersioned == 1:
                        edit.startEditing(False, True)
                        edit.startOperation()
                    else:           
                        edit.startEditing(False, False)
                        edit.startOperation()


                    arcpy.AddMessage("Deleting records from {}".format(table_path))


                    with arcpy.da.UpdateCursor(table_path, field) as cursor:
                        for row in cursor:
                            if row[0] in idList:
                                idList.remove(row[0])
                                del_count += 1
                                cursor.deleteRow()

    except Exception as e:
        if edit.isEditing:
            edit.stopEditing(False)

        arcpy.AddError('{}'.format(e))
        tb = sys.exc_info()[2]
        arcpy.AddError("Failed at Line %i" % tb.tb_lineno)

    finally:
        if del_count != dict_cnt:
            arcpy.AddWarning("Copied {} records from {} but deleted {} records".format(dict_cnt, table, del_count))
        if edit.isEditing:
            edit.stopEditing(True)


# -----------------------------
# Update REVCHECKRUNTABLE and REVBATCHRUNTABLE records
# -----------------------------
def CopyRunTables(Reviewer_Workspace, Out_Reviewer_Workspace, SessionClause, OutSessionID, CheckRunMap, BatchRunMatches, CheckRunMatches):
    try:

        REVCHECKRUN = getFullPath(Reviewer_Workspace, "REVCHECKRUNTABLE")
        REVBATCHRUN = getFullPath(Reviewer_Workspace, "REVBATCHRUNTABLE")

        Out_REVCHECKRUN = getFullPath(Out_Reviewer_Workspace, "REVCHECKRUNTABLE")
        Out_REVBATCHRUN = getFullPath(Out_Reviewer_Workspace, "REVBATCHRUNTABLE")

        if REVCHECKRUN != '' and REVBATCHRUN != '' and Out_REVCHECKRUN != '' and Out_REVBATCHRUN != '':


            CheckRunIDsSelected = CheckRunMap.keys()

            # See if there are CHECKRUNIDs that did not return errors
            with arcpy.da.SearchCursor(REVCHECKRUN, ["CHECKRUNID"], SessionClause) as cursor:
                for row in cursor:
                    # if the check run ID is in the sessions but not copied, skip the id
                    if not row[0] in CheckRunIDsSelected:
                        check_guid = '{' + str(uuid.uuid4()).upper() + '}'
                        CheckRunMap[row[0]] = check_guid



            # Get a list of the batch run IDs for the chosen sessions
            BatchRunIDs = []
            CheckRunIDs = CheckRunMap.keys()
            with arcpy.da.SearchCursor(REVCHECKRUN, ['CHECKRUNID', 'BATCHRUNID'], SessionClause) as cursor:
                for row in cursor:
                    if row[0] in CheckRunIDs:
                        BatchRunIDs.append(row[1])

            BatchRunIDs = list(set(BatchRunIDs))

            # ------------------------
            # Copy REVBATCHRUN records
            # ------------------------

            if len(BatchRunIDs) > 0:
                # Get the fields from the input and output databases
                batchrun_fieldnames = [x.name for x in arcpy.ListFields(REVBATCHRUN)]
                out_batchrun_fieldnames = [x.name for x in arcpy.ListFields(Out_REVBATCHRUN)]

                REVBATCHRUN_FIELDS = sorted(batchrun_fieldnames)
                OUT_REVBATCHRUN_FIELDS = sorted(batchrun_fieldnames)

                REVBATCHRUN_RECORDID_INDEX = REVBATCHRUN_FIELDS.index("RECORDID")

                in_id_field = 'GLOBALID'
                out_id_field = 'GLOBALID'

                if in_id_field not in batchrun_fieldnames:
                    in_id_field = 'ID'

                REVBATCHRUN_UID_INDEX = REVBATCHRUN_FIELDS.index(in_id_field)


                # at 10.6 the field named GlobalID changed to be ID
                if out_id_field not in out_batchrun_fieldnames:
                    out_id_field = 'ID'
                    OUT_REVBATCHRUN_FIELDS.remove(in_id_field)
                    OUT_REVBATCHRUN_FIELDS.insert(REVBATCHRUN_UID_INDEX, out_id_field)

                # Find the batch run records that related to the copied check run records
                whereClause = MakeInClause(REVBATCHRUN, in_id_field, BatchRunIDs)

                # Used to track the new GlobalIDs
                batchRunOrigGlobalIDsByNewRecordID = {}


                BatchRunMatches["InIDField"] = "RECORDID"
                BatchRunMatches["OutIDField"] = "RECORDID"


                insert = arcpy.da.InsertCursor(Out_REVBATCHRUN, OUT_REVBATCHRUN_FIELDS)
                newGlobalIDsByOrigGlobalID = {}
                try:

                    with arcpy.da.SearchCursor(REVBATCHRUN, REVBATCHRUN_FIELDS, whereClause) as cursor:
                        for row in cursor:

                            rowValues = list(row)

                            # get the original values
                            batchRunRecordID = row[REVBATCHRUN_RECORDID_INDEX]
                            origGlobalID = row[REVBATCHRUN_UID_INDEX]

                            # if the output field is named ID, will not auto populate
                            # new guid.  Create a new guid
                            if out_id_field == 'ID':
                                newGlobalID = '{' + str(uuid.uuid4()).upper() + '}'
                                rowValues[REVBATCHRUN_UID_INDEX] = newGlobalID
                                newGlobalIDsByOrigGlobalID[origGlobalID] = newGlobalID

                            # insert a new row
                            newRecordID = insert.insertRow((rowValues))

                            # create lists and dict to make old and new values
                            BatchRunMatches[batchRunRecordID] = newRecordID


                            # if the field is GlobalID, a new guid was autogenerated
                            # need to do extra steps to map to new GUID.  Get list of record ID
                            if out_id_field == 'GLOBALID':
                                batchRunOrigGlobalIDsByNewRecordID[newRecordID] = origGlobalID


                finally:
                    del insert


                if out_id_field == 'GLOBALID' and len(batchRunOrigGlobalIDsByNewRecordID) >= 1:
                    outBatchRunRecordIDs = batchRunOrigGlobalIDsByNewRecordID.keys()
                    # Get a map of original GlobalIDs to new GlobalIDs
                    whereClause = MakeInClause(Out_REVBATCHRUN, "RECORDID", outBatchRunRecordIDs)

                    with arcpy.da.SearchCursor(Out_REVBATCHRUN, ['RECORDID',out_id_field], whereClause) as cursor:

                        for row in cursor:
                            recID = row[0]

                            if recID in batchRunOrigGlobalIDsByNewRecordID:
                                origGlobalID = batchRunOrigGlobalIDsByNewRecordID[recID]
                                newGlobalID = row[1]

                                newGlobalIDsByOrigGlobalID[origGlobalID] = newGlobalID
                            else:
                                arcpy.AddWarning("Unable to find original GLOBALID for RECORDID {0}".format(recID))



            # ------------------------
            # Copy REVCHECKRUN records and update BatchRunID
            # ------------------------
            if len(CheckRunMap) >= 1:
                REVCHECKRUN_FIELDS = [x.name for x in arcpy.ListFields(REVCHECKRUN)]
                REVCHECKRUN_RECORDID_INDEX = REVCHECKRUN_FIELDS.index("RECORDID")
                REVCHECKRUN_CHECKRUNID_INDEX = REVCHECKRUN_FIELDS.index("CHECKRUNID")
                REVCHECKRUN_SESSIONID_INDEX = REVCHECKRUN_FIELDS.index("SESSIONID")
                REVCHECKRUN_BATCHRUNID_INDEX = REVCHECKRUN_FIELDS.index("BATCHRUNID")
                REVCHECKRUN_CHECKRUNPROPS_INDEX = REVCHECKRUN_FIELDS.index("CHECKRUNPROPERTIES")

                insert = arcpy.da.InsertCursor(Out_REVCHECKRUN, REVCHECKRUN_FIELDS)

                CheckRunMatches["InIDField"] = "RECORDID"
                CheckRunMatches["OutIDField"] = "RECORDID"

                try:
                    with arcpy.da.SearchCursor(REVCHECKRUN, REVCHECKRUN_FIELDS, SessionClause) as cursor:
                        for row in cursor:
                            rowValues = list(row)

                            # get check run ids for records
                            checkRunID = rowValues[REVCHECKRUN_CHECKRUNID_INDEX]

                            if checkRunID in CheckRunMap:
                                newCheckRunID = CheckRunMap[checkRunID]
                                rowValues[REVCHECKRUN_CHECKRUNID_INDEX] = newCheckRunID

                                batchRunRecordID = rowValues[REVCHECKRUN_RECORDID_INDEX]

                                # get batch run ids for records and add to list
                                batchRunID = rowValues[REVCHECKRUN_BATCHRUNID_INDEX]
                                if batchRunID in newGlobalIDsByOrigGlobalID:
                                    rowValues[REVCHECKRUN_BATCHRUNID_INDEX] = newGlobalIDsByOrigGlobalID[batchRunID]

                                # update the session Id
                                rowValues[REVCHECKRUN_SESSIONID_INDEX] = OutSessionID

                                # Check BLOB field, BLOB fields cannot be set to None
                                if rowValues[REVCHECKRUN_CHECKRUNPROPS_INDEX] is None:
                                    rowValues[REVCHECKRUN_CHECKRUNPROPS_INDEX] = bytearray()

                                # add row
                                newRecordID = insert.insertRow(rowValues)

                                CheckRunMatches[batchRunRecordID] = newRecordID
                finally:
                    del insert

        else:
            arcpy.AddWarning("Unable to identify REVCHECKRUNTABLE or REVBATCHRUNTABLE in Reviewer Workspace "
            " No records from these tables will be copied.")

    except Exception as e:
        arcpy.AddError('{}'.format(e))
        tb = sys.exc_info()[2]
        arcpy.AddError("Failed at Line %i" % tb.tb_lineno)

    finally:
        return CheckRunMatches, BatchRunMatches

# ------------------------------------------------------------------
# Deletes rows from an input table/feature class given a list of IDs
# ------------------------------------------------------------------
def main():

    # Script arguments
    Reviewer_Workspace = arcpy.GetParameterAsText(0)
    Sessions = arcpy.GetParameterAsText(1)
    RecordClause = arcpy.GetParameterAsText(3)
    Out_Reviewer_Workspace = arcpy.GetParameterAsText(4)
    Out_Exist_Session = arcpy.GetParameterAsText(5)
    Delete = arcpy.GetParameterAsText(6)
    createLog = arcpy.GetParameterAsText(7)

    # Input sessions to Python list
    SessionsList = Sessions.split(";")

    # Strip any trailing/leading ' that might exist
    for i,value in enumerate(SessionsList):
        SessionsList[i] = value.strip("'")

    # ----------------------------------------
    # Check for version compatablity
    # ----------------------------------------
    in_version = DetermineVersion(Reviewer_Workspace)
    out_version = DetermineVersion(Out_Reviewer_Workspace)

    #Check compatablity of databases.
    # check to see if either database is pre 10.3
    if in_version == 'Pre10.3' or out_version == 'Pre10.3':
        if in_version == 'Pre10.3':
            db_compatability = 'Incompatable'
            arcpy.AddError("Input workspace is out of date."
            "Please upgrade the workspace {} to version 10.3 or higher".format(Reviewer_Workspace))
        if out_version == 'Pre10.3':
            db_compatability = 'Incompatable'
            arcpy.AddError("Output workspace is out of date."
            "Please upgrade the workspace {} to version 10.3 or higher".format(Out_Reviewer_Workspace))

    # if one or more of the reviewer workspaces has a schema newer than 10.6 we
    # do not know what has changed so we will not support it
    elif in_version == 'Unsupported' or out_version == 'Unsupported':
        if in_version == 'Unsupported':
            db_compatability = 'Incompatable'
            arcpy.AddError("The version of the reviewer workspace {} is not supported."
            "The tool is designed for earlier version of the Reviewer Workspace Schema".format(Reviewer_Workspace))
        if out_version == 'Unsupported':
            db_compatability = 'Incompatable'
            arcpy.AddError("The version of the reviewer workspace {} is not supported."
            "  The tool is designed for earlier version of the Reviewer Workspace Schema".format(Out_Reviewer_Workspace))

    # if the output version is newer than the input version, will require upgrade
    elif in_version == 'Pre10.6' and out_version != 'Pre10.6':
        db_compatability = '10.6Upgrade'
    # if the output version is before 10.6 and the input version is newer, cannot migrate records
    elif in_version != 'Pre10.6' and out_version == 'Pre10.6':
        db_compatability = 'Incompatable'
        arcpy.AddError("Input workspace is newer than the output workspace."
        "Please upgrade the output workspace {} to the latest version or select a different output workspace".format(Out_Reviewer_Workspace, in_version))
    # if both versions are Pre 10.6
    elif in_version == 'Pre10.6' and out_version == 'Pre10.6':
        db_compatability = 'Old'
    # if both versions are Post 10.6
    else:
        db_compatability = 'New'

    # ----------------------------------------
    # If versions are compatable, copy records
    # ----------------------------------------
    if db_compatability != 'Incompatable':

        # ---  Paths to tables in Input Reviewer workspace tables ---
        REVTABLEMAIN = getFullPath(Reviewer_Workspace, "REVTABLEMAIN", True)
        SessionsTable = getFullPath(Reviewer_Workspace, "REVSESSIONTABLE", True)
        REVTABLELOC = getFullPath(Reviewer_Workspace, "REVTABLELOCATION")
        REVTABLEPOINT = getFullPath(Reviewer_Workspace, "REVTABLEPOINT")
        REVTABLELINE = getFullPath(Reviewer_Workspace, "REVTABLELINE")
        REVTABLEPOLY = getFullPath(Reviewer_Workspace, "REVTABLEPOLY")

        # --- Paths to tables in Output Reviewer workspace tables ---
        Out_REVTABLEMAIN = getFullPath(Out_Reviewer_Workspace, "REVTABLEMAIN", True)
        Out_SessionsTable = getFullPath(Out_Reviewer_Workspace, "REVSESSIONTABLE", True)
        Out_REVTABLELOC = getFullPath(Out_Reviewer_Workspace, "REVTABLELOCATION")
        Out_REVTABLEPOINT = getFullPath(Out_Reviewer_Workspace, "REVTABLEPOINT")
        Out_REVTABLELINE = getFullPath(Out_Reviewer_Workspace, "REVTABLELINE")
        Out_REVTABLEPOLY = getFullPath(Out_Reviewer_Workspace, "REVTABLEPOLY")

        # List of selected session IDs
        sessionIDs = []

        # The main (REVTABLEMAIN) where clause
        WhereClause = ""

        # Output session ID
        OutSessionID = 0

        # Variables used for logging purposes
        PointMatches = {}
        PointMatches['tableName'] = 'REVTABLEPOINT'
        LineMatches = {}
        LineMatches['tableName'] = 'REVTABLELINE'
        PolyMatches = {}
        PolyMatches['tableName'] = 'REVTABLEPOLY'
        MisMatches = {}
        MisMatches['tableName'] = 'REVTABLELOCATION'
        RowMatches = {}
        RowMatches['tableName'] = 'REVTABLEMAIN'
        BatchRunMatches = {}
        BatchRunMatches['tableName'] = 'REVBATCHRUNTABLE'
        CheckRunMatches = {}
        CheckRunMatches['tableName'] = 'REVCHECKRUNTABLE'

        log_dicts = [RowMatches, PointMatches, LineMatches, PolyMatches, MisMatches, BatchRunMatches, CheckRunMatches]

        ErrorCount = 0

        # Get editor for editing
        edit = arcpy.da.Editor(Out_Reviewer_Workspace)

        try:
            # Start an edit session
            desc = arcpy.Describe(Out_REVTABLEMAIN)
            if desc.canVersion == 1 and desc.isVersioned == 1:
                edit.startEditing(False, True)
                edit.startOperation()
            else:
                edit.startEditing(False, False)
                edit.startOperation()

            # ----------------------------------------
            # Build Where Clause for selecting records
            # ----------------------------------------

            # Get the IDs for the input session(s)
            rowcount = int(arcpy.GetCount_management(SessionsTable).getOutput(0))
            inSession_dict = {}
            with arcpy.da.SearchCursor(SessionsTable, ["SESSIONID", "SESSIONNAME"]) as rows:
                for row in rows:
                    # I am interested in value in column SessionName
                    if row[1] in SessionsList:
                        sessionIDs.append(row[0])
                        inSession_dict[row[0]] = row[1]

            sessioncount = len(sessionIDs)

            # If you did not select all the sessions, make a whereclause to select
            # only features from the desired sessions

            WhereClause = ''
            if sessioncount != rowcount:
                WhereClause = MakeInClause(Out_SessionsTable, "SESSIONID", sessionIDs)

            SessionClause = WhereClause

            # Append any information from the entered expression to the where clause
            if RecordClause:
                if WhereClause != '':
                    WhereClause = WhereClause + " AND " + RecordClause
                else:
                    WhereClause = RecordClause

            wherecount = len(WhereClause)

            # Limit the length of the where clause to 1000 characters.
            # Certain dbms types limit the length of where clause predicates.
            # Predicates that use IN or OR operators may be limited to 1000 candidates.
            if wherecount > 1000:
                arcpy.AddError("The where clause is too long. There are either too many sessions selected or the Expression parameter (RecordClause) is too long.")
                sys.exit(0)
            else:
                # Get output session id
                outSession_dict = {}
                with arcpy.da.SearchCursor(Out_SessionsTable, ["SESSIONID", "SESSIONNAME"]) as rows:
                    for row in rows:
                        # I am interested in value in column SessionName
                        if row[1] == Out_Exist_Session:
                            OutSessionID = row[0]
                            outSession_dict[row[0]] = row[1]

                arcpy.AddMessage("Output Reviewer Session id is {0}".format(OutSessionID))

                Match = CompareSR(REVTABLEPOINT, Out_REVTABLEPOINT)

                # -------------------------
                # Copy RevTableMain records
                # -------------------------
                arcpy.AddMessage("Copying RevTableMain Records")

                in_revtable_fields = [x.name for x in arcpy.ListFields(REVTABLEMAIN)]
                out_revtable_fields = [x.name for x in arcpy.ListFields(Out_REVTABLEMAIN)]

                UNIQUE_REVTABLEMAIN_FIELDS = (set(in_revtable_fields) & set(out_revtable_fields))
                READ_REVTABLEMAIN_FIELDS = sorted(list(UNIQUE_REVTABLEMAIN_FIELDS))

                WRITE_REVTABLEMAIN_FIELDS = sorted(list(UNIQUE_REVTABLEMAIN_FIELDS))


                REVTABLEMAIN_SESSIONID_INDEX = READ_REVTABLEMAIN_FIELDS.index("SESSIONID")
                REVTABLEMAIN_CHECKRUNID_INDEX = READ_REVTABLEMAIN_FIELDS.index("CHECKRUNID")
                REVTABLEMAIN_GEOMETRYTYPE_INDEX = READ_REVTABLEMAIN_FIELDS.index("GEOMETRYTYPE")

                in_id_field = 'RECORDID'
                if in_version != 'Pre10.6':
                    in_id_field = 'ID'
                REVTABLEMAIN_ID_INDEX = READ_REVTABLEMAIN_FIELDS.index(in_id_field)

                out_id_field = 'RECORDID'
                if out_version != 'Pre10.6':
                    RECORD_GUID_FIELD = 'ID'
                    if 'ID' not in WRITE_REVTABLEMAIN_FIELDS:
                        idx = WRITE_REVTABLEMAIN_FIELDS.index("RECORDID")
                        WRITE_REVTABLEMAIN_FIELDS.remove("RECORDID")
                        WRITE_REVTABLEMAIN_FIELDS.insert(idx, u'ID')
                        out_id_field = "ID"


                REVTABLEMAIN_ID_INDEX = READ_REVTABLEMAIN_FIELDS.index(in_id_field)
                CheckRunMap = {}
                RowMatches["InIDField"] = in_id_field
                inID_index = READ_REVTABLEMAIN_FIELDS.index(in_id_field)
                RowMatches["OutIDField"] = out_id_field
                outID_index = WRITE_REVTABLEMAIN_FIELDS.index(out_id_field)
                insert = arcpy.da.InsertCursor(Out_REVTABLEMAIN, WRITE_REVTABLEMAIN_FIELDS)

                try:
                    with arcpy.da.SearchCursor(REVTABLEMAIN, READ_REVTABLEMAIN_FIELDS, where_clause=WhereClause) as scursor:                        
                        for row in scursor:
                            ErrorCount += 1
                            # Data Access SearchCursor's return a tuple which are immutable.  We need to create a mutable type so
                            # we can update the SESSIONID value before inserting the record into the output table.
                            rowValues = list(row)

                            sessionID = rowValues[REVTABLEMAIN_SESSIONID_INDEX]
                            checkRunID = rowValues[REVTABLEMAIN_CHECKRUNID_INDEX]
                            inRecordID = rowValues[REVTABLEMAIN_ID_INDEX]

                            # Get CHECKRUNID value
                            checkRunID = rowValues[REVTABLEMAIN_CHECKRUNID_INDEX]

                            if checkRunID :
                                # Create new check run IDs
                                if checkRunID in CheckRunMap:
                                    check_guid = CheckRunMap[checkRunID]
                                else:
                                    check_guid = '{' + str(uuid.uuid4()).upper() + '}'
                                    CheckRunMap[checkRunID] = check_guid

                                rowValues[REVTABLEMAIN_CHECKRUNID_INDEX] = check_guid

                            # Update the record id map

                            geomType = rowValues[REVTABLEMAIN_GEOMETRYTYPE_INDEX]

                            rowValues[REVTABLEMAIN_SESSIONID_INDEX] = OutSessionID

                            if db_compatability != 'Old':
                                record_guid = '{' + str(uuid.uuid4()).upper() + '}'
                                rowValues[REVTABLEMAIN_ID_INDEX] = record_guid

                            outRecordID = insert.insertRow(rowValues)

                            if db_compatability == 'Old':
                                outID = outRecordID
                            else:
                                outID = record_guid
                            RowMatches[inRecordID] = outID

                finally:
                    del insert

                # ---------------------------
                # Copy REVTABLEPOINT features
                # ---------------------------
                arcpy.AddMessage("Copying Point Geometries")
                CopyGeometryFeatures(REVTABLEPOINT, Out_REVTABLEPOINT, SessionClause, RowMatches, OutSessionID, PointMatches)

                # --------------------------
                # Copy REVTABLELINE features
                # --------------------------
                arcpy.AddMessage("Copying Line Geometries")
                CopyGeometryFeatures(REVTABLELINE, Out_REVTABLELINE, SessionClause, RowMatches, OutSessionID, LineMatches)

                # --------------------------
                # Copy REVTABLEPOLY features
                # --------------------------
                arcpy.AddMessage("Copying Polygon Geometries")
                CopyGeometryFeatures(REVTABLEPOLY, Out_REVTABLEPOLY, SessionClause, RowMatches, OutSessionID, PolyMatches)

                # ------------------------
                # Copy REVTABLELOC records
                # ------------------------
                arcpy.AddMessage("Copying Location Records")
                CopyGeometryFeatures(REVTABLELOC, Out_REVTABLELOC, SessionClause, RowMatches, OutSessionID, MisMatches)

                # ------------------------
                # Copy Batch Job info records
                # ------------------------
                CopyRunTables(Reviewer_Workspace, Out_Reviewer_Workspace, SessionClause, OutSessionID, CheckRunMap, BatchRunMatches, CheckRunMatches)

                # Save edits
                if edit.isEditing:
                    edit.stopEditing(True)


                # If successfully make it to the end of the script and delete is set to
                # true - delete the records
                if Delete == "true":
                    for dictionary in log_dicts:
                        DeleteRows(Reviewer_Workspace, dictionary)

            # --------------
            # Create logfile
            # --------------
            if createLog == "true":
                # Determine output folder
                (filepath, filename) = os.path.split(Out_Reviewer_Workspace)

                # Does user have write-access to the output folder?
                if not os.access(filepath, os.W_OK):
                    # Determine where this user has access to write
                    scratch = arcpy.env.scratchWorkspace
                    try:
                        if os.access(scratch, os.W_OK):
                            (filepath, fileName) = os.path.split(scratch)
                        else:
                            createLog = 'false'
                    except Exception as e:
                        arcpy.AddWarning("Cannot write logfile.  An error occurred while trying to access the geoprocessing scratch workspace: " + e.message)
                        createLog = "false"

            # if we will be able to write output log
            if createLog == "true":
                now = datetime.datetime.now()
                time_str = now.strftime("%Y%m%dT%H%M%S")

                logfile = filepath + "\\CopyDataReviewerRecordsLog_" + time_str \
                + ".txt"

                log = open(logfile, "w")

                # Write Header information
                log.write("Source Workspace: " + Reviewer_Workspace + "\n")
                log.write("Input Session(s): \n")
                for sessionId, sessionName in inSession_dict.items():
                    log.write("    {}: {}\n".format(sessionId, sessionName))


                log.write("\nTarget Workspace: " + Out_Reviewer_Workspace + "\n")
                log.write("Output Session: \n")

                for sessionId, sessionName in outSession_dict.items():
                    log.write("    {}: {}\n".format(sessionId, sessionName))

                del sessionId
                del sessionName

            else:
                log = ''

            # if there is at least one error
            #loop through logging dictionaries and get counts
            log_dicts = [PointMatches, LineMatches, PolyMatches, MisMatches, RowMatches]

            summarydict = {}
            for matches in log_dicts:
                summarydict = SummarizeDictionaries(log, matches, summarydict)

            arcpy.AddMessage("\n")
            for dict_name, cnt in summarydict.items():
                msg = "Total Records from {}: {}".format(dict_name, cnt)

                arcpy.AddMessage(msg)
                if createLog == "true":
                    log.write(msg + "\n")

            if createLog == "true":
                log.close()
                arcpy.AddMessage("\n")
                arcpy.AddMessage("Logfile created at: " + logfile)


        except Exception as e:

            if edit.isEditing:

                arcpy.AddMessage("Rolling back edits made to " + Out_Reviewer_Workspace)
                edit.stopEditing(False)

            arcpy.AddError('{}'.format(e))
            tb = sys.exc_info()[2]
            arcpy.AddError("Failed at Line %i" % tb.tb_lineno)



if __name__ == '__main__':
    main()
