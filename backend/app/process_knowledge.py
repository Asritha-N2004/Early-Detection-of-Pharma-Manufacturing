"""Demonstration investigation hypotheses, never established causes or control advice."""
RULES={
 'fermentation':{
  'temperature':('FER-THERMAL','Investigate thermal-control performance or temperature-sensor integrity'),
  'pH':('FER-PH','Investigate pH measurement, feed history and mixing consistency'),
  'dissolved_oxygen':('FER-DO','Investigate oxygen measurement, aeration and agitation history'),
  'feed_rate':('FER-FEED','Investigate feed delivery records and feed-sensor calibration'),
  'biomass':('FER-GROWTH','Investigate growth-stage context and biomass sampling evidence'),
  'glucose':('FER-METABOLIC','Investigate substrate sampling and feed-related metabolic hypotheses'),
  'lactate':('FER-METABOLIC','Investigate metabolite sampling and metabolic-shift hypotheses'),
  'titer':('FER-TITER','Investigate titer assay, sampling and batch-stage history')},
 'tablet':{
  'moisture':('TAB-MOISTURE','Investigate granulation/drying history and moisture-sampling consistency'),
  'compression_force':('TAB-COMPRESSION','Investigate compression-force measurement and tooling records'),
  'tablet_weight':('TAB-WEIGHT','Investigate weight measurements, feed consistency and compression history'),
  'blend_uniformity':('TAB-BLEND','Investigate blend sampling, mixing history and uniformity evidence')},
 'sterile':{
  'differential_pressure':('STR-PRESSURE','Investigate pressure-sensor integrity and HVAC/door-event records'),
  'particle_count':('STR-PARTICLE','Investigate particle-counter validity and environmental/equipment records'),
  'environmental_monitoring':('STR-EM','Investigate environmental sample handling and contamination indicators; do not presume contamination'),
  'equipment_status':('STR-EQUIPMENT','Investigate equipment-status and maintenance records')},
 'liquid':{
  'viscosity':('LIQ-VISCOSITY','Investigate viscosity measurement, mixing history and temperature context'),
  'pH':('LIQ-PH','Investigate pH measurement, mixing and material-addition records'),
  'filling_weight':('LIQ-FILL','Investigate fill-weight measurement and filling-equipment records'),
  'mixing_speed':('LIQ-MIX','Investigate mixing-speed measurement and mixing-stage history')}
}

def hypothesis(process,parameter):
    id,cause=RULES.get(process,{}).get(parameter,('GEN-SENSOR',f'Investigate {parameter} process or sensor instability'))
    return {'id':id,'cause':cause,'basis':'Demonstration engineering hypothesis; verify against site-approved procedures and source evidence.'}
