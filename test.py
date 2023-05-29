
p1 = dict()
park1 = {'ptz1': '0.4551;0.1714;0.5013;0.1714;0.5013;0.9886;0.3538;0.9829;0.4551;0.1714'}
p1['ptz_id'] = '1'
p1['ptz'] = ''
p1['coordinate'] = park1

ptz_params = [p1]

# if [True for i in ptz_params if 'coordinate' in i]:
#     print(ptz_params)

print(ptz_params['coordinate'])